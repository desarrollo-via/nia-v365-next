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
    compose_private_protected_history_session_adapter,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionExecutionPlan,
    coordinate_protected_history_session_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_entrypoint import (
    ProtectedHistorySessionEntrypointSnapshot,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m16.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m16-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m16-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m16-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m16.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m16-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m16-installations",
}


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("resources must stay fictional and unused")


def ephemeral_inputs():
    return BitrixHistoryR0EphemeralInputs(
        expected_text_sha256="b" * 64,
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
        anchor=BitrixHistoryR0Anchor(901, 701),
        preflight_ready=True,
        dialog_read_calls=1,
        resources_closed=True,
    )
    return ProtectedInMemoryHandoffOwner(
        helper=helper_snapshot(), handoff=handoff, preflight_calls=1
    )


def received_result():
    return BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.RECEIVED,
        reason="fictional-m16-private-result",
        dialog_read_calls=2,
        history_read_calls=1,
        new_last_message_detected=True,
        candidate_count=1,
        controlled_message_verified=True,
        resources_closed=True,
    )


class ProtectedSessionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def _plan(self, confirmation=HISTORY_R0_ARM_CONFIRMATION):
        return ProtectedHistorySessionExecutionPlan(
            dotenv_path=Path("fictional-m16.env"),
            inputs=ephemeral_inputs(),
            resources_factory=FakeResourcesFactory(),
            preflight_client_builder=lambda **_kwargs: object(),
            reader_client_builder=lambda **_kwargs: object(),
            confirmation_reader=lambda: asyncio.sleep(0, result=confirmation),
            authorization_timeout_seconds=5,
            reader_timeout_seconds=5,
        )

    def _adapter_composer(self, calls, captured):
        async def owner_preparer(**kwargs):
            calls["owner"] += 1
            kwargs["on_settings_ready"](load_settings(FICTIONAL_VALUES))
            return waiting_owner()

        def armed_reader_composer(**_kwargs):
            calls["composer"] += 1

            async def reader(_anchor):
                calls["reader"] += 1
                return received_result()

            return reader

        def compose_adapter(**kwargs):
            calls["adapter"] += 1
            adapter = compose_private_protected_history_session_adapter(
                **kwargs,
                owner_preparer=owner_preparer,
                armed_reader_composer=armed_reader_composer,
            )
            captured.append(adapter)
            return adapter

        return compose_adapter

    async def test_default_preview_binds_m14_only_and_calls_nothing_operational(self):
        snapshot = await coordinate_protected_history_session_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertFalse(snapshot.execution_requested)
        self.assertEqual(snapshot.launcher_compositions, 1)
        self.assertEqual(snapshot.adapter_compositions, 0)
        self.assertEqual(snapshot.entrypoint_calls, 0)
        self.assertEqual(snapshot.owner_builder_calls, 0)
        self.assertEqual(snapshot.reader_calls, 0)
        self.assertTrue(snapshot.private_state_cleared)

    async def test_full_double_lifecycle_links_m14_m15_m13_once(self):
        calls = {"adapter": 0, "owner": 0, "composer": 0, "reader": 0}
        captured = []

        snapshot = await coordinate_protected_history_session_once(
            execute=True,
            plan=self._plan(),
            compose_adapter=self._adapter_composer(calls, captured),
        )

        self.assertEqual(snapshot.state, "RECEIVED")
        self.assertEqual(calls, {name: 1 for name in calls})
        self.assertEqual(snapshot.launcher_compositions, 1)
        self.assertEqual(snapshot.adapter_compositions, 1)
        self.assertEqual(snapshot.entrypoint_calls, 1)
        self.assertEqual(snapshot.owner_builder_calls, 1)
        self.assertEqual(snapshot.settings_capture_calls, 1)
        self.assertEqual(snapshot.confirmation_calls, 1)
        self.assertEqual(snapshot.reader_factory_calls, 1)
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertEqual(snapshot.cleanup_calls, 1)
        self.assertTrue(snapshot.private_state_cleared)
        self.assertFalse(captured[0].snapshot().settings_retained)
        self.assertFalse(captured[0].snapshot().owner_retained)

    async def test_execute_without_plan_stops_before_adapter_and_entrypoint(self):
        adapter_calls = 0

        def compose_adapter(**_kwargs):
            nonlocal adapter_calls
            adapter_calls += 1
            raise AssertionError("adapter must not compose")

        snapshot = await coordinate_protected_history_session_once(
            execute=True,
            compose_adapter=compose_adapter,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertTrue(snapshot.execution_requested)
        self.assertEqual(snapshot.launcher_compositions, 1)
        self.assertEqual(snapshot.adapter_compositions, 0)
        self.assertEqual(snapshot.entrypoint_calls, 0)
        self.assertEqual(adapter_calls, 0)

    async def test_wrong_confirmation_cancels_and_clears(self):
        calls = {"adapter": 0, "owner": 0, "composer": 0, "reader": 0}
        captured = []

        snapshot = await coordinate_protected_history_session_once(
            execute=True,
            plan=self._plan("NO AUTORIZADO"),
            compose_adapter=self._adapter_composer(calls, captured),
        )

        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertEqual(calls["owner"], 1)
        self.assertEqual(calls["composer"], 0)
        self.assertEqual(calls["reader"], 0)
        self.assertTrue(snapshot.private_state_cleared)
        self.assertFalse(captured[0].snapshot().settings_retained)

    async def test_launcher_failure_stops_before_plan_or_adapter(self):
        snapshot = await coordinate_protected_history_session_once(
            execute=True,
            plan=self._plan(),
            compose_launcher=lambda: (_ for _ in ()).throw(
                RuntimeError("fictional-m16-launcher-detail")
            ),
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.launcher_compositions, 1)
        self.assertEqual(snapshot.adapter_compositions, 0)
        self.assertEqual(snapshot.entrypoint_calls, 0)
        self.assertNotIn("launcher-detail", repr(asdict(snapshot)))

    async def test_adapter_failure_is_redacted_and_fail_closed(self):
        snapshot = await coordinate_protected_history_session_once(
            execute=True,
            plan=self._plan(),
            compose_adapter=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("fictional-m16-adapter-detail")
            ),
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.adapter_compositions, 1)
        self.assertEqual(snapshot.entrypoint_calls, 0)
        self.assertTrue(snapshot.private_state_cleared)
        self.assertNotIn("adapter-detail", repr(asdict(snapshot)))

    async def test_allowlisted_entrypoint_failure_category_is_propagated(self):
        calls = {"adapter": 0, "owner": 0, "composer": 0, "reader": 0}
        captured = []

        async def no_go_entrypoint(**_kwargs):
            return ProtectedHistorySessionEntrypointSnapshot(
                state="NO-GO",
                reason="fictional-private-reason",
                failure_category="dialog_identity_mismatch",
                execution_requested=True,
                owner_calls=1,
                resources_closed=True,
            )

        snapshot = await coordinate_protected_history_session_once(
            execute=True,
            plan=self._plan(),
            compose_adapter=self._adapter_composer(calls, captured),
            session_entrypoint=no_go_entrypoint,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_category, "dialog_identity_mismatch")
        self.assertNotIn("private-reason", repr(asdict(snapshot)))

    async def test_history_shape_categories_reach_coordinator_without_reason(self):
        categories = (
            "reader_history_envelope_invalid",
            "reader_history_collections_invalid",
            "reader_history_fields_invalid",
        )
        for category in categories:
            with self.subTest(category=category):
                calls = {"adapter": 0, "owner": 0, "composer": 0, "reader": 0}
                captured = []

                async def no_go_entrypoint(**_kwargs):
                    return ProtectedHistorySessionEntrypointSnapshot(
                        state="NO-GO",
                        reason="fictional-m44-private-reason",
                        failure_category=category,
                        execution_requested=True,
                        owner_calls=1,
                        resources_closed=True,
                    )

                snapshot = await coordinate_protected_history_session_once(
                    execute=True,
                    plan=self._plan(),
                    compose_adapter=self._adapter_composer(calls, captured),
                    session_entrypoint=no_go_entrypoint,
                )

                self.assertEqual(snapshot.state, "NO-GO")
                self.assertEqual(snapshot.failure_category, category)
                self.assertNotIn("private-reason", repr(asdict(snapshot)))

    async def test_entrypoint_cancellation_clears_adapter_and_reraises(self):
        calls = {"adapter": 0, "owner": 0, "composer": 0, "reader": 0}
        captured = []

        async def cancelled_entrypoint(**_kwargs):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await coordinate_protected_history_session_once(
                execute=True,
                plan=self._plan(),
                compose_adapter=self._adapter_composer(calls, captured),
                session_entrypoint=cancelled_entrypoint,
            )
        self.assertFalse(captured[0].snapshot().settings_retained)
        self.assertFalse(captured[0].snapshot().owner_retained)

    def test_execution_plan_repr_is_redacted(self):
        plan = self._plan()
        self.assertEqual(repr(plan), "ProtectedHistorySessionExecutionPlan(<redacted>)")
        serialized = repr(plan)
        for private in (*FICTIONAL_VALUES.values(), "fictional-m16.env", "b" * 64):
            self.assertNotIn(private, serialized)

    def test_source_has_no_direct_external_or_interactive_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_coordinator.py"
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
