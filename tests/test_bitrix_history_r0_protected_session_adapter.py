import asyncio
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
)
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
from bitrix_connector.bitrix_history_r0_protected_session_adapter import (
    ProtectedHistorySessionDependencyAdapter,
    compose_private_protected_history_session_adapter,
)
from bitrix_connector.bitrix_history_r0_protected_session_entrypoint import (
    execute_protected_history_session_entrypoint_once,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m15.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m15-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m15-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m15-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m15.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m15-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m15-installations",
}


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("resources must not be built by the adapter")


def fictional_settings():
    return load_settings(FICTIONAL_VALUES)


def ephemeral_inputs():
    return BitrixHistoryR0EphemeralInputs(
        expected_text_sha256="a" * 64,
        window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


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
        reason="fictional-m15-private-result",
        dialog_read_calls=2,
        history_read_calls=1,
        new_last_message_detected=True,
        candidate_count=1,
        controlled_message_verified=True,
        resources_closed=True,
    )


class ProtectedSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    def _compose(self, *, owner=None, calls=None, composer=None):
        calls = calls if calls is not None else {
            "owner": 0,
            "composer": 0,
            "reader": 0,
        }
        selected_owner = owner or waiting_owner()

        async def owner_preparer(**kwargs):
            calls["owner"] += 1
            kwargs["on_settings_ready"](fictional_settings())
            return selected_owner

        def default_composer(**kwargs):
            calls["composer"] += 1
            self.assertIsNotNone(kwargs["settings"].bitrix_member_id)

            async def reader(_anchor):
                calls["reader"] += 1
                return received_result()

            return reader

        adapter = compose_private_protected_history_session_adapter(
            dotenv_path=Path("fictional-m15.env"),
            inputs=ephemeral_inputs(),
            resources_factory=FakeResourcesFactory(),
            preflight_client_builder=lambda **_kwargs: object(),
            reader_client_builder=lambda **_kwargs: object(),
            owner_preparer=owner_preparer,
            armed_reader_composer=composer or default_composer,
        )
        return adapter, calls

    def test_composition_is_inert_redacted_and_retains_nothing(self):
        calls = {"owner": 0, "composer": 0, "reader": 0}
        adapter, calls = self._compose(calls=calls)

        self.assertIsInstance(adapter, ProtectedHistorySessionDependencyAdapter)
        self.assertEqual(repr(adapter), "ProtectedHistorySessionDependencyAdapter(<redacted>)")
        self.assertEqual(adapter.snapshot().state, "PREPARED")
        self.assertFalse(adapter.snapshot().settings_retained)
        self.assertFalse(adapter.snapshot().owner_retained)
        self.assertEqual(calls, {name: 0 for name in calls})

    async def test_full_m13_lifecycle_uses_private_bridge_once_and_clears(self):
        adapter, calls = self._compose()
        emitted = []

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=adapter.build_owner_once,
            confirmation_reader=lambda: asyncio.sleep(
                0, result=HISTORY_R0_ARM_CONFIRMATION
            ),
            reader_factory=adapter.build_reader_once,
            private_state_cleanup=adapter.clear_private_state,
            execute=True,
            authorization_timeout_seconds=5,
            reader_timeout_seconds=5,
            emit=emitted.append,
        )

        self.assertEqual(result.state, "RECEIVED")
        self.assertEqual(calls, {"owner": 1, "composer": 1, "reader": 1})
        snapshot = adapter.snapshot()
        self.assertEqual(snapshot.state, "CLEARED")
        self.assertEqual(snapshot.owner_builder_calls, 1)
        self.assertEqual(snapshot.settings_capture_calls, 1)
        self.assertEqual(snapshot.reader_factory_calls, 1)
        self.assertEqual(snapshot.cleanup_calls, 1)
        self.assertFalse(snapshot.settings_retained)
        self.assertFalse(snapshot.owner_retained)
        self.assertEqual(
            [item.state for item in emitted],
            ["WAITING-AUTHORIZATION", "ARMED", "RECEIVED", "CLOSED"],
        )
        serialized = repr(asdict(snapshot)) + repr(adapter)
        for private in (*FICTIONAL_VALUES.values(), "900", "700", "private-result"):
            self.assertNotIn(private, serialized)

    async def test_wrong_confirmation_clears_before_reader_composition(self):
        adapter, calls = self._compose()

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=adapter.build_owner_once,
            confirmation_reader=lambda: asyncio.sleep(0, result="NO AUTORIZADO"),
            reader_factory=adapter.build_reader_once,
            private_state_cleanup=adapter.clear_private_state,
            execute=True,
        )

        self.assertEqual(result.state, "CANCELLED")
        self.assertEqual(calls, {"owner": 1, "composer": 0, "reader": 0})
        self.assertFalse(adapter.snapshot().settings_retained)
        self.assertFalse(adapter.snapshot().owner_retained)
        self.assertEqual(adapter.snapshot().cleanup_calls, 1)

    async def test_no_go_owner_discards_settings_without_composer(self):
        adapter, calls = self._compose(owner=no_go_owner())

        result = await execute_protected_history_session_entrypoint_once(
            owner_builder=adapter.build_owner_once,
            confirmation_reader=lambda: asyncio.sleep(
                0, result=HISTORY_R0_ARM_CONFIRMATION
            ),
            reader_factory=adapter.build_reader_once,
            private_state_cleanup=adapter.clear_private_state,
            execute=True,
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(calls, {"owner": 1, "composer": 0, "reader": 0})
        self.assertFalse(adapter.snapshot().settings_retained)
        self.assertFalse(adapter.snapshot().owner_retained)

    async def test_cancellation_clears_private_state_and_reraises(self):
        adapter, calls = self._compose()

        async def cancel():
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await execute_protected_history_session_entrypoint_once(
                owner_builder=adapter.build_owner_once,
                confirmation_reader=cancel,
                reader_factory=adapter.build_reader_once,
                private_state_cleanup=adapter.clear_private_state,
                execute=True,
            )

        self.assertEqual(calls, {"owner": 1, "composer": 0, "reader": 0})
        self.assertFalse(adapter.snapshot().settings_retained)
        self.assertFalse(adapter.snapshot().owner_retained)

    async def test_reader_factory_rejects_before_armed_and_clears(self):
        adapter, calls = self._compose()

        with self.assertRaisesRegex(RuntimeError, "adapter_not_armed"):
            adapter.build_reader_once()

        self.assertEqual(calls, {"owner": 0, "composer": 0, "reader": 0})
        self.assertFalse(adapter.snapshot().settings_retained)
        self.assertFalse(adapter.snapshot().owner_retained)

    def test_invalid_dependency_is_rejected_without_private_detail(self):
        with self.assertRaisesRegex(
            TypeError, "protected_history_session_adapter_dependency_invalid"
        ):
            compose_private_protected_history_session_adapter(
                dotenv_path=Path("fictional-m15.env"),
                inputs=ephemeral_inputs(),
                resources_factory=object(),
                preflight_client_builder=lambda: None,
                reader_client_builder=lambda: None,
            )

    def test_source_has_no_direct_external_or_interactive_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_adapter.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "keyring",
            "get_access_token",
            "refresh_access_token",
            "get_dialog(",
            "get_session_history(",
            "imopenlines",
            "httpx.AsyncClient(",
            "AsyncIOMotorClient(",
            "subprocess",
            "socket",
            "argparse",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
