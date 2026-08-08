import asyncio
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_handoff import (
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
)
from bitrix_connector.bitrix_history_r0_handoff_cli import (
    HISTORY_R0_ARM_CONFIRMATION,
)
from bitrix_connector.bitrix_history_r0_preflight import BitrixHistoryR0Anchor
from bitrix_connector.bitrix_history_r0_protected_handoff_composition import (
    ProtectedInMemoryHandoffOwner,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    ProtectedHelperSnapshot,
    ProtectedHelperState,
)
from bitrix_connector.bitrix_history_r0_protected_session_entrypoint import (
    ProtectedHistorySessionEntrypointSnapshot,
    execute_protected_history_session_entrypoint_once,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)


ROOT = Path(__file__).resolve().parents[1]


def helper_snapshot():
    return ProtectedHelperSnapshot(
        state=ProtectedHelperState.READY,
        reason="protected_helper_completed",
        protected_source_opened=True,
        required_values_present=True,
        operation_completed=True,
        resources_closed=True,
        source_read_calls=7,
        operation_calls=1,
    )


def waiting_owner():
    handoff = BitrixHistoryR0InMemoryHandoff(
        state=BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
        reason="bitrix_history_handoff_waiting_authorization",
        anchor=BitrixHistoryR0Anchor(900, 700),
        preflight_ready=True,
        dialog_read_calls=1,
        resources_closed=True,
    )
    return ProtectedInMemoryHandoffOwner(
        helper=helper_snapshot(),
        handoff=handoff,
        preflight_calls=1,
    )


def no_go_owner():
    handoff = BitrixHistoryR0InMemoryHandoff(
        state=BitrixHistoryR0HandoffState.NO_GO,
        reason="bitrix_history_barrier_degraded",
        resources_closed=True,
    )
    return ProtectedInMemoryHandoffOwner(
        helper=helper_snapshot(),
        handoff=handoff,
        preflight_calls=1,
    )


def received_result():
    return BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.RECEIVED,
        reason="fictional-m13-private-result",
        dialog_read_calls=2,
        history_read_calls=1,
        new_last_message_detected=True,
        candidate_count=1,
        controlled_message_verified=True,
        resources_closed=True,
    )


class ProtectedSessionEntrypointTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_preview_calls_nothing(self):
        calls = {"owner": 0, "confirmation": 0, "factory": 0}
        emitted = []

        async def owner_builder():
            calls["owner"] += 1
            raise AssertionError("owner must not run")

        async def confirmation_reader():
            calls["confirmation"] += 1
            raise AssertionError("confirmation must not run")

        def reader_factory():
            calls["factory"] += 1
            raise AssertionError("factory must not run")

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=owner_builder,
            confirmation_reader=confirmation_reader,
            reader_factory=reader_factory,
            emit=emitted.append,
        )

        self.assertEqual(result.state, "PREPARED")
        self.assertFalse(result.execution_requested)
        self.assertEqual(calls, {"owner": 0, "confirmation": 0, "factory": 0})
        self.assertEqual(emitted, [result])

    async def test_literal_gate_then_deferred_reader_runs_once(self):
        owner = waiting_owner()
        calls = {"owner": 0, "confirmation": 0, "factory": 0, "reader": 0}
        anchors = []
        emitted = []

        async def owner_builder():
            calls["owner"] += 1
            return owner

        async def confirmation_reader():
            calls["confirmation"] += 1
            return HISTORY_R0_ARM_CONFIRMATION

        async def reader(anchor):
            calls["reader"] += 1
            anchors.append((anchor.session_id, anchor.baseline_last_message_id))
            return received_result()

        def reader_factory():
            calls["factory"] += 1
            return reader

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=owner_builder,
            confirmation_reader=confirmation_reader,
            reader_factory=reader_factory,
            execute=True,
            authorization_timeout_seconds=5,
            reader_timeout_seconds=5,
            emit=emitted.append,
        )

        self.assertEqual(result.state, "RECEIVED")
        self.assertEqual(
            calls,
            {"owner": 1, "confirmation": 1, "factory": 1, "reader": 1},
        )
        self.assertEqual(anchors, [(900, 700)])
        self.assertEqual(
            [item.state for item in emitted],
            ["WAITING-AUTHORIZATION", "ARMED", "RECEIVED", "CLOSED"],
        )
        serialized = "".join(repr(asdict(item)) for item in emitted)
        for private in (
            "900",
            "700",
            "session_id",
            "last_message_id",
            "private-result",
        ):
            self.assertNotIn(private, serialized)

    async def test_wrong_literal_cancels_before_reader_factory(self):
        owner = waiting_owner()
        factory_calls = 0
        emitted = []

        def reader_factory():
            nonlocal factory_calls
            factory_calls += 1
            raise AssertionError("factory must not run")

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=lambda: asyncio.sleep(0, result=owner),
            confirmation_reader=lambda: asyncio.sleep(0, result="NO AUTORIZADO"),
            reader_factory=reader_factory,
            execute=True,
            emit=emitted.append,
        )

        self.assertEqual(result.state, "CANCELLED")
        self.assertEqual(factory_calls, 0)
        self.assertEqual(
            [item.state for item in emitted],
            ["WAITING-AUTHORIZATION", "CANCELLED", "CLOSED"],
        )

    async def test_no_go_owner_stops_before_confirmation_and_factory(self):
        owner = no_go_owner()
        confirmation_calls = 0
        factory_calls = 0

        async def confirmation_reader():
            nonlocal confirmation_calls
            confirmation_calls += 1
            return HISTORY_R0_ARM_CONFIRMATION

        def reader_factory():
            nonlocal factory_calls
            factory_calls += 1
            return lambda _anchor: asyncio.sleep(0, result=received_result())

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=lambda: asyncio.sleep(0, result=owner),
            confirmation_reader=confirmation_reader,
            reader_factory=reader_factory,
            execute=True,
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(confirmation_calls, 0)
        self.assertEqual(factory_calls, 0)

    async def test_invalid_limits_stop_before_owner(self):
        owner_calls = 0

        async def owner_builder():
            nonlocal owner_calls
            owner_calls += 1
            return waiting_owner()

        for authorization, reader in ((0, 5), (301, 5), (5, 0), (5, 301)):
            with self.subTest(authorization=authorization, reader=reader):
                result = await execute_protected_history_session_entrypoint_once(
                    owner_builder=owner_builder,
                    confirmation_reader=lambda: asyncio.sleep(
                        0,
                        result=HISTORY_R0_ARM_CONFIRMATION,
                    ),
                    reader_factory=lambda: object(),
                    execute=True,
                    authorization_timeout_seconds=authorization,
                    reader_timeout_seconds=reader,
                )
                self.assertEqual(result.state, "NO-GO")
        self.assertEqual(owner_calls, 0)

    async def test_reader_factory_failure_is_redacted_and_closes(self):
        owner = waiting_owner()
        emitted = []

        def reader_factory():
            raise RuntimeError("fictional-m13-private-factory-detail")

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=lambda: asyncio.sleep(0, result=owner),
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            reader_factory=reader_factory,
            execute=True,
            emit=emitted.append,
        )

        self.assertIsInstance(result, ProtectedHistorySessionEntrypointSnapshot)
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.reader_factory_calls, 1)
        self.assertFalse(result.resources_closed)
        self.assertEqual(emitted[-1].state, "CLOSED")
        self.assertNotIn("private-factory-detail", repr(asdict(result)))

    async def test_reader_timeout_fails_closed_without_retry(self):
        owner = waiting_owner()
        reader_calls = 0

        async def reader(_anchor):
            nonlocal reader_calls
            reader_calls += 1
            await asyncio.Event().wait()
            return received_result()

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=lambda: asyncio.sleep(0, result=owner),
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            reader_factory=lambda: reader,
            execute=True,
            reader_timeout_seconds=0.001,
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.reader_calls, 1)
        self.assertEqual(reader_calls, 1)
        self.assertFalse(owner.snapshot().anchor_available)

    async def test_confirmation_cancellation_closes_and_reraises(self):
        owner = waiting_owner()

        async def confirmation_reader():
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await execute_protected_history_session_entrypoint_once(
                owner_builder=lambda: asyncio.sleep(0, result=owner),
                confirmation_reader=confirmation_reader,
                reader_factory=lambda: object(),
                execute=True,
            )
        self.assertEqual(owner.snapshot().state, "CLOSED")
        self.assertFalse(owner.snapshot().anchor_available)

    def test_source_is_programmatic_default_off_and_has_no_direct_services(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_entrypoint.py"
        ).read_text(encoding="utf-8")
        self.assertIn("execute: bool = False", source)
        self.assertIn("HISTORY_R0_ARM_CONFIRMATION", source)
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "keyring",
            "httpx",
            "requests",
            "pymongo",
            "motor",
            "get_access_token",
            "refresh_access_token",
            "imopenlines",
            "subprocess",
            "socket",
            "argparse",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
