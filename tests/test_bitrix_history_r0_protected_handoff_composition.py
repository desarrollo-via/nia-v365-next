import asyncio
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_handoff import (
    BitrixHistoryR0HandoffDecision,
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_protected_handoff_composition import (
    prepare_protected_dotenv_history_handoff_once,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m10.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m10-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m10-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m10-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m10.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m10-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m10-installations",
}


class FakeSource:
    def __init__(self, *, fail_open=False, fail_close=False):
        self.fail_open = fail_open
        self.fail_close = fail_close
        self.open_calls = 0
        self.read_calls = 0
        self.close_calls = 0

    async def open(self):
        self.open_calls += 1
        if self.fail_open:
            raise RuntimeError("fictional-m10-open-detail")

    async def read(self, name):
        self.read_calls += 1
        return bytearray(FICTIONAL_VALUES[name], "utf-8")

    async def close(self):
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("fictional-m10-close-detail")


def ready_outcome():
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.READY,
            reason="bitrix_history_preflight_ready",
            dialog_read_calls=1,
            history_read_calls=0,
            dialog_verified=True,
            session_verified=True,
            baseline_captured=True,
            resources_closed=True,
        ),
        BitrixHistoryR0Anchor(
            session_id=900,
            baseline_last_message_id=700,
        ),
    )


def no_go_outcome():
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.NO_GO,
            reason="bitrix_history_dialog_mismatch",
            dialog_read_calls=1,
            history_read_calls=0,
            resources_closed=True,
        )
    )


class ProtectedHandoffCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def _prepare(
        self,
        *,
        source=None,
        outcome=None,
        executor=None,
        builder=None,
        on_settings_ready=None,
    ):
        source = source or FakeSource()
        outcome = outcome or ready_outcome()
        preflight_calls = []
        factory = object()
        client_builder = object()

        async def default_executor(**kwargs):
            preflight_calls.append(kwargs)
            return outcome

        kwargs = {}
        if builder is not None:
            kwargs["handoff_builder"] = builder
        if on_settings_ready is not None:
            kwargs["on_settings_ready"] = on_settings_ready
        owner = await prepare_protected_dotenv_history_handoff_once(
            dotenv_path=Path("fictional-m10.env"),
            resources_factory=factory,
            client_builder=client_builder,
            source_builder=lambda _path: source,
            execute_preflight=executor or default_executor,
            **kwargs,
        )
        return owner, source, preflight_calls, factory, client_builder

    async def test_safe_settings_callback_runs_once_after_ready_handoff(self):
        captured = []

        owner, source, calls, _factory, _client = await self._prepare(
            on_settings_ready=captured.append,
        )

        self.assertEqual(owner.snapshot().state, "WAITING-AUTHORIZATION")
        self.assertEqual(len(captured), 1)
        self.assertEqual(source.close_calls, 1)
        self.assertEqual(len(calls), 1)
        serialized = repr(owner) + repr(asdict(owner.snapshot()))
        for value in FICTIONAL_VALUES.values():
            self.assertNotIn(value, serialized)

    async def test_ready_outcome_is_owned_privately_once_and_closes(self):
        outcome = ready_outcome()
        received = []

        def builder(candidate):
            received.append(candidate)
            return BitrixHistoryR0InMemoryHandoff.from_preflight(candidate)

        owner, source, calls, factory, client_builder = await self._prepare(
            outcome=outcome,
            builder=builder,
        )
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "WAITING-AUTHORIZATION")
        self.assertTrue(snapshot.anchor_available)
        self.assertEqual(snapshot.source_read_calls, 7)
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertEqual(snapshot.dialog_read_calls, 1)
        self.assertEqual(snapshot.history_read_calls, 0)
        self.assertEqual(snapshot.mutation_calls, 0)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(source.open_calls, 1)
        self.assertEqual(source.close_calls, 1)
        self.assertIs(received[0], outcome)
        self.assertIs(calls[0]["resources_factory"], factory)
        self.assertIs(calls[0]["client_builder"], client_builder)

        serialized = repr(owner) + repr(asdict(snapshot))
        for private in ("900", "700", "session_id", "last_message_id"):
            self.assertNotIn(private, serialized)
        for name, value in FICTIONAL_VALUES.items():
            self.assertNotIn(name, serialized)
            self.assertNotIn(value, serialized)

        closed = await owner.close()
        self.assertEqual(closed.state, "CLOSED")
        self.assertFalse(closed.anchor_available)

    async def test_no_go_outcome_never_exposes_anchor(self):
        owner, source, calls, _factory, _client = await self._prepare(
            outcome=no_go_outcome()
        )
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_category, "dialog_identity_mismatch")
        self.assertFalse(snapshot.anchor_available)
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertEqual(snapshot.history_read_calls, 0)
        self.assertEqual(snapshot.mutation_calls, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(source.close_calls, 1)

    async def test_source_failure_stops_before_preflight(self):
        source = FakeSource(fail_open=True)
        owner, source, calls, _factory, _client = await self._prepare(source=source)
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.failure_category,
            "protected_source_or_settings_failed",
        )
        self.assertEqual(snapshot.preflight_calls, 0)
        self.assertEqual(len(calls), 0)
        self.assertEqual(source.read_calls, 0)
        self.assertEqual(source.close_calls, 1)
        self.assertTrue(snapshot.resources_closed)

    async def test_invalid_preflight_outcome_fails_closed(self):
        async def invalid_executor(**_kwargs):
            return object()

        owner, source, _calls, _factory, _client = await self._prepare(
            executor=invalid_executor
        )
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_category, "other_safe_failure")
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertFalse(snapshot.anchor_available)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(source.close_calls, 1)

    async def test_invalid_handoff_candidate_fails_closed(self):
        def invalid_builder(_outcome):
            return object()

        owner, _source, calls, _factory, _client = await self._prepare(
            builder=invalid_builder
        )
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertEqual(len(calls), 1)
        self.assertFalse(snapshot.anchor_available)

    async def test_source_close_failure_discards_created_anchor(self):
        source = FakeSource(fail_close=True)
        built = []

        def builder(outcome):
            handoff = BitrixHistoryR0InMemoryHandoff.from_preflight(outcome)
            built.append(handoff)
            return handoff

        owner, _source, calls, _factory, _client = await self._prepare(
            source=source,
            builder=builder,
        )
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertFalse(snapshot.anchor_available)
        self.assertFalse(snapshot.resources_closed)
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(built[0].snapshot().state, BitrixHistoryR0HandoffState.CLOSED)
        self.assertFalse(built[0].snapshot().anchor_available)

    async def test_preflight_cancellation_closes_source_and_returns_cancelled(self):
        async def cancelled_executor(**_kwargs):
            raise asyncio.CancelledError

        owner, source, _calls, _factory, _client = await self._prepare(
            executor=cancelled_executor
        )
        snapshot = owner.snapshot()

        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertFalse(snapshot.anchor_available)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(source.close_calls, 1)

    async def test_owner_arms_once_without_exposing_handoff_or_anchor(self):
        owner, _source, _calls, _factory, _client = await self._prepare()
        gate_calls = 0

        async def gate():
            nonlocal gate_calls
            gate_calls += 1
            return BitrixHistoryR0HandoffDecision.ARM

        armed = await owner.wait_for_authorization(
            authorization_gate=gate,
            timeout_seconds=5,
        )

        self.assertEqual(armed.state, "ARMED")
        self.assertEqual(armed.authorization_calls, 1)
        self.assertEqual(gate_calls, 1)
        self.assertTrue(armed.anchor_available)
        self.assertEqual(armed.history_read_calls, 0)
        self.assertEqual(armed.mutation_calls, 0)
        self.assertTrue(armed.resources_closed)
        serialized = repr(owner) + repr(asdict(armed))
        for private in ("900", "700", "session_id", "last_message_id"):
            self.assertNotIn(private, serialized)

        repeated = await owner.wait_for_authorization(
            authorization_gate=gate,
            timeout_seconds=5,
        )
        self.assertEqual(repeated, armed)
        self.assertEqual(gate_calls, 1)

    async def test_owner_cancel_discards_anchor(self):
        owner, _source, _calls, _factory, _client = await self._prepare()

        cancelled = await owner.wait_for_authorization(
            authorization_gate=lambda: asyncio.sleep(
                0,
                result=BitrixHistoryR0HandoffDecision.CANCEL,
            ),
            timeout_seconds=5,
        )

        self.assertEqual(cancelled.state, "CANCELLED")
        self.assertEqual(cancelled.authorization_calls, 1)
        self.assertFalse(cancelled.anchor_available)
        self.assertEqual(cancelled.history_read_calls, 0)
        self.assertEqual(cancelled.mutation_calls, 0)

    async def test_owner_invalid_timeout_fails_before_calling_gate(self):
        owner, _source, _calls, _factory, _client = await self._prepare()
        gate_calls = 0

        async def gate():
            nonlocal gate_calls
            gate_calls += 1
            return BitrixHistoryR0HandoffDecision.ARM

        snapshot = await owner.wait_for_authorization(
            authorization_gate=gate,
            timeout_seconds=301,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.authorization_calls, 1)
        self.assertEqual(gate_calls, 0)
        self.assertFalse(snapshot.anchor_available)

    async def test_owner_timeout_and_gate_failure_fail_closed(self):
        async def timeout_gate():
            await asyncio.Event().wait()
            return BitrixHistoryR0HandoffDecision.ARM

        async def failed_gate():
            raise RuntimeError("fictional-m11-private-detail")

        for gate, timeout_seconds in ((timeout_gate, 0.001), (failed_gate, 5)):
            with self.subTest(gate=gate.__name__):
                owner, _source, _calls, _factory, _client = await self._prepare()
                snapshot = await owner.wait_for_authorization(
                    authorization_gate=gate,
                    timeout_seconds=timeout_seconds,
                )
                self.assertEqual(snapshot.state, "NO-GO")
                self.assertEqual(snapshot.authorization_calls, 1)
                self.assertFalse(snapshot.anchor_available)
                self.assertEqual(snapshot.history_read_calls, 0)
                self.assertEqual(snapshot.mutation_calls, 0)
                self.assertNotIn("private-detail", repr(asdict(snapshot)))

    async def test_owner_task_cancellation_closes_and_reraises(self):
        owner, _source, _calls, _factory, _client = await self._prepare()
        started = asyncio.Event()

        async def gate():
            started.set()
            await asyncio.Event().wait()
            return BitrixHistoryR0HandoffDecision.ARM

        task = asyncio.create_task(
            owner.wait_for_authorization(
                authorization_gate=gate,
                timeout_seconds=5,
            )
        )
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        snapshot = owner.snapshot()
        self.assertEqual(snapshot.state, "CLOSED")
        self.assertEqual(snapshot.authorization_calls, 1)
        self.assertFalse(snapshot.anchor_available)

    async def test_no_go_owner_never_invokes_authorization_gate(self):
        owner, _source, _calls, _factory, _client = await self._prepare(
            outcome=no_go_outcome()
        )
        gate_calls = 0

        async def gate():
            nonlocal gate_calls
            gate_calls += 1
            return BitrixHistoryR0HandoffDecision.ARM

        snapshot = await owner.wait_for_authorization(
            authorization_gate=gate,
            timeout_seconds=5,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.authorization_calls, 0)
        self.assertEqual(gate_calls, 0)
        self.assertFalse(snapshot.anchor_available)

    async def _armed_owner(self):
        owner, _source, _calls, _factory, _client = await self._prepare()
        armed = await owner.wait_for_authorization(
            authorization_gate=lambda: asyncio.sleep(
                0,
                result=BitrixHistoryR0HandoffDecision.ARM,
            ),
            timeout_seconds=5,
        )
        self.assertEqual(armed.state, "ARMED")
        return owner

    async def test_owner_delivers_anchor_to_reader_once_and_redacts_result(self):
        owner = await self._armed_owner()
        received_anchors = []

        async def reader(anchor):
            received_anchors.append(
                (anchor.session_id, anchor.baseline_last_message_id)
            )
            return BitrixHistoryR0Result(
                status=BitrixHistoryR0Status.RECEIVED,
                reason="fictional-m12-private-success-detail",
                dialog_read_calls=2,
                history_read_calls=1,
                new_last_message_detected=True,
                candidate_count=1,
                controlled_message_verified=True,
                resources_closed=True,
            )

        snapshot = await owner.run_armed_reader_once(reader)

        self.assertEqual(received_anchors, [(900, 700)])
        self.assertEqual(snapshot.state, "RECEIVED")
        self.assertEqual(snapshot.reason, "protected_handoff_continuity_received")
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertEqual(snapshot.history_read_calls, 1)
        self.assertEqual(snapshot.mutation_calls, 0)
        self.assertFalse(snapshot.anchor_available)
        self.assertTrue(snapshot.resources_closed)
        serialized = repr(owner) + repr(asdict(snapshot))
        for private in (
            "900",
            "700",
            "session_id",
            "last_message_id",
            "private-success-detail",
        ):
            self.assertNotIn(private, serialized)

        repeated = await owner.run_armed_reader_once(reader)
        self.assertEqual(repeated, snapshot)
        self.assertEqual(received_anchors, [(900, 700)])

    async def test_owner_normalizes_reader_no_go_and_discards_anchor(self):
        owner = await self._armed_owner()

        async def reader(_anchor):
            return BitrixHistoryR0Result(
                status=BitrixHistoryR0Status.NO_GO,
                reason="fictional-m12-private-no-go-detail",
                dialog_read_calls=3,
                history_read_calls=0,
                resources_closed=True,
            )

        snapshot = await owner.run_armed_reader_once(reader)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.reason,
            "protected_handoff_continuity_reader_no_go",
        )
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertFalse(snapshot.anchor_available)
        self.assertEqual(
            snapshot.failure_category,
            "reader_other_safe_failure",
        )
        self.assertNotIn("private-no-go-detail", repr(asdict(snapshot)))

    async def test_owner_exposes_allowlisted_reader_timeout_category(self):
        owner = await self._armed_owner()

        async def reader(_anchor):
            return BitrixHistoryR0Result(
                status=BitrixHistoryR0Status.NO_GO,
                reason="bitrix_history_wait_timeout",
                dialog_read_calls=36,
                history_read_calls=0,
                resources_closed=True,
            )

        snapshot = await owner.run_armed_reader_once(reader)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_category, "reader_wait_timeout")
        self.assertEqual(snapshot.dialog_read_calls, 36)
        self.assertEqual(snapshot.history_read_calls, 0)

    async def test_owner_exposes_safe_history_shape_categories_only(self):
        cases = (
            (
                "bitrix_history_invalid_envelope",
                "reader_history_envelope_invalid",
            ),
            (
                "bitrix_history_invalid_collections",
                "reader_history_collections_invalid",
            ),
            (
                "bitrix_history_invalid_fields",
                "reader_history_fields_invalid",
            ),
        )
        for reason, expected_category in cases:
            with self.subTest(reason=reason):
                owner = await self._armed_owner()

                async def reader(_anchor, current=reason):
                    return BitrixHistoryR0Result(
                        status=BitrixHistoryR0Status.NO_GO,
                        reason=current,
                        dialog_read_calls=1,
                        history_read_calls=1,
                        new_last_message_detected=True,
                        resources_closed=True,
                    )

                snapshot = await owner.run_armed_reader_once(reader)

                self.assertEqual(snapshot.state, "NO-GO")
                self.assertEqual(snapshot.failure_category, expected_category)
                self.assertEqual(snapshot.history_read_calls, 1)
                serialized = repr(asdict(snapshot))
                self.assertNotIn(reason, serialized)
                self.assertNotIn("fictional-m10-secret", serialized)

    async def test_owner_reader_failure_is_closed_and_redacted(self):
        owner = await self._armed_owner()
        reader_calls = 0

        async def reader(_anchor):
            nonlocal reader_calls
            reader_calls += 1
            raise RuntimeError("fictional-m12-private-failure-detail")

        snapshot = await owner.run_armed_reader_once(reader)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertEqual(reader_calls, 1)
        self.assertFalse(snapshot.anchor_available)
        self.assertFalse(snapshot.resources_closed)
        self.assertEqual(snapshot.failure_category, "reader_failed")
        self.assertNotIn("private-failure-detail", repr(asdict(snapshot)))
        await owner.run_armed_reader_once(reader)
        self.assertEqual(reader_calls, 1)

    async def test_owner_invalid_reader_result_fails_closed(self):
        owner = await self._armed_owner()

        async def reader(_anchor):
            return object()

        snapshot = await owner.run_armed_reader_once(reader)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertFalse(snapshot.anchor_available)
        self.assertFalse(snapshot.resources_closed)
        self.assertEqual(
            snapshot.failure_category,
            "reader_failed",
        )

    async def test_owner_reader_cancellation_closes_and_reraises(self):
        owner = await self._armed_owner()

        async def reader(_anchor):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await owner.run_armed_reader_once(reader)

        snapshot = owner.snapshot()
        self.assertEqual(snapshot.state, "CLOSED")
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertFalse(snapshot.anchor_available)

    async def test_owner_never_calls_reader_before_arm(self):
        owner, _source, _calls, _factory, _client = await self._prepare()
        reader_calls = 0

        async def reader(_anchor):
            nonlocal reader_calls
            reader_calls += 1
            return object()

        snapshot = await owner.run_armed_reader_once(reader)

        self.assertEqual(snapshot.state, "WAITING-AUTHORIZATION")
        self.assertEqual(snapshot.reader_calls, 0)
        self.assertEqual(reader_calls, 0)
        self.assertTrue(snapshot.anchor_available)

    def test_module_has_no_direct_environment_cli_network_or_service_access(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_handoff_composition.py"
        ).read_text(encoding="utf-8")
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
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
