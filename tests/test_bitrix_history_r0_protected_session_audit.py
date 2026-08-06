import asyncio
import inspect
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
)
from bitrix_connector.bitrix_history_r0_handoff import (
    MAX_AUTHORIZATION_WAIT_SECONDS,
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
)
from bitrix_connector.bitrix_history_r0_handoff_cli import (
    HISTORY_R0_ARM_CONFIRMATION,
)
from bitrix_connector.bitrix_history_r0_preflight import BitrixHistoryR0Anchor
from bitrix_connector.bitrix_history_r0_preflight_composition import (
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
)
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
from bitrix_connector.bitrix_history_r0_protected_session_contract import (
    PROTECTED_HISTORY_SESSION_CONTRACT,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionExecutionPlan,
    coordinate_protected_history_session_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_entrypoint import (
    execute_protected_history_session_entrypoint_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
    PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
    compose_protected_history_session_execution_gate,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m18.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m18-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m18-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m18-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m18.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m18-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m18-installations",
}


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("M18 audit must not build real resources")


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
        anchor=BitrixHistoryR0Anchor(902, 702),
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
        reason="fictional-m18-private-result",
        dialog_read_calls=2,
        history_read_calls=1,
        new_last_message_detected=True,
        candidate_count=1,
        controlled_message_verified=True,
        resources_closed=True,
    )


class ProtectedSessionHermeticAuditTests(unittest.IsolatedAsyncioTestCase):
    def _components(self, *, inner_confirmation=HISTORY_R0_ARM_CONFIRMATION, reader=None):
        calls = {
            "adapter": 0,
            "owner": 0,
            "composer": 0,
            "reader": 0,
            "coordinator": 0,
        }
        captured = []

        async def owner_preparer(**kwargs):
            calls["owner"] += 1
            kwargs["on_settings_ready"](load_settings(FICTIONAL_VALUES))
            return waiting_owner()

        async def default_reader(_anchor):
            calls["reader"] += 1
            return received_result()

        def armed_reader_composer(**_kwargs):
            calls["composer"] += 1
            return reader or default_reader

        def compose_adapter(**kwargs):
            calls["adapter"] += 1
            adapter = compose_private_protected_history_session_adapter(
                **kwargs,
                owner_preparer=owner_preparer,
                armed_reader_composer=armed_reader_composer,
            )
            captured.append(adapter)
            return adapter

        plan = ProtectedHistorySessionExecutionPlan(
            dotenv_path=Path("fictional-m18.env"),
            inputs=BitrixHistoryR0EphemeralInputs(
                expected_text_sha256="d" * 64,
                window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
            resources_factory=FakeResourcesFactory(),
            preflight_client_builder=lambda **_kwargs: object(),
            reader_client_builder=lambda **_kwargs: object(),
            confirmation_reader=lambda: asyncio.sleep(
                0, result=inner_confirmation
            ),
            authorization_timeout_seconds=5,
            reader_timeout_seconds=0.01,
        )

        async def coordinator(**kwargs):
            calls["coordinator"] += 1
            return await coordinate_protected_history_session_once(
                **kwargs,
                compose_adapter=compose_adapter,
            )

        gate = compose_protected_history_session_execution_gate(
            plan=plan, coordinator=coordinator
        )
        return gate, calls, captured

    def test_frozen_contract_matches_code_limits_and_default_off(self):
        contract = PROTECTED_HISTORY_SESSION_CONTRACT
        signature = inspect.signature(coordinate_protected_history_session_once)

        self.assertEqual(contract.phase, "M18")
        self.assertIs(signature.parameters["execute"].default, False)
        self.assertEqual(
            contract.preflight_timeout_seconds,
            DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            contract.authorization_timeout_seconds,
            MAX_AUTHORIZATION_WAIT_SECONDS,
        )
        self.assertEqual(contract.reader_timeout_seconds, MAX_AUTHORIZATION_WAIT_SECONDS)
        self.assertEqual(contract.gate_attempt_limit, 1)
        self.assertEqual(contract.coordinator_attempt_limit, 1)
        self.assertEqual(contract.owner_attempt_limit, 1)
        self.assertEqual(contract.preflight_attempt_limit, 1)
        self.assertEqual(contract.reader_attempt_limit, 1)
        self.assertFalse(contract.real_execution_authorized)
        self.assertFalse(contract.message_request_authorized)

    async def test_complete_m17_to_m13_double_path_has_exact_counts_and_cleanup(self):
        gate, calls, captured = self._components()
        result = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(result.state, "RECEIVED")
        self.assertEqual(calls, {name: 1 for name in calls})
        self.assertEqual(result.gate_attempts, 1)
        self.assertEqual(result.coordinator_calls, 1)
        self.assertEqual(result.launcher_compositions, 1)
        self.assertEqual(result.adapter_compositions, 1)
        self.assertEqual(result.entrypoint_calls, 1)
        self.assertEqual(result.owner_builder_calls, 1)
        self.assertEqual(result.settings_capture_calls, 1)
        self.assertEqual(result.confirmation_calls, 1)
        self.assertEqual(result.reader_factory_calls, 1)
        self.assertEqual(result.reader_calls, 1)
        self.assertEqual(result.cleanup_calls, 1)
        self.assertTrue(result.private_state_cleared)
        self.assertFalse(captured[0].snapshot().settings_retained)
        self.assertFalse(captured[0].snapshot().owner_retained)
        serialized = repr(asdict(result)) + repr(captured[0])
        for private in (*FICTIONAL_VALUES.values(), "902", "702", "private-result"):
            self.assertNotIn(private, serialized)

    async def test_outer_rejection_stops_before_entire_inner_chain(self):
        gate, calls, captured = self._components()
        result = await gate.execute_once("NO AUTORIZADO")

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(calls, {name: 0 for name in calls})
        self.assertEqual(captured, [])

    async def test_inner_rejection_cancels_before_reader_and_cleans(self):
        gate, calls, captured = self._components(inner_confirmation="NO AUTORIZADO")
        result = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(result.state, "CANCELLED")
        self.assertEqual(calls["coordinator"], 1)
        self.assertEqual(calls["owner"], 1)
        self.assertEqual(calls["composer"], 0)
        self.assertEqual(calls["reader"], 0)
        self.assertTrue(result.private_state_cleared)
        self.assertFalse(captured[0].snapshot().settings_retained)

    async def test_reader_timeout_is_terminal_clean_and_not_retried(self):
        reader_calls = 0

        async def blocked_reader(_anchor):
            nonlocal reader_calls
            reader_calls += 1
            await asyncio.Event().wait()

        gate, calls, captured = self._components(reader=blocked_reader)
        result = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )
        retry = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(retry.state, "NO-GO")
        self.assertEqual(reader_calls, 1)
        self.assertEqual(calls["coordinator"], 1)
        self.assertTrue(result.private_state_cleared)
        self.assertFalse(captured[0].snapshot().settings_retained)

    def test_contract_is_public_safe_and_contains_no_identity_or_message(self):
        payload = asdict(PROTECTED_HISTORY_SESSION_CONTRACT)
        serialized = repr(payload)
        for private in (
            "chat78733",
            "78733",
            "614949",
            "373259",
            "245339",
            "member_id",
            "expected_text",
            "dotenv_path",
        ):
            self.assertNotIn(private, serialized)

    def test_m13_m18_sources_have_no_direct_interactive_or_service_start(self):
        names = (
            "bitrix_history_r0_protected_session_entrypoint.py",
            "bitrix_history_r0_protected_session_launcher.py",
            "bitrix_history_r0_protected_session_adapter.py",
            "bitrix_history_r0_protected_session_coordinator.py",
            "bitrix_history_r0_protected_session_execution_gate.py",
            "bitrix_history_r0_protected_session_contract.py",
        )
        forbidden = (
            "subprocess",
            "socket",
            "argparse",
            "input(",
            "Start-Process",
            "uvicorn",
            "FastAPI(",
        )
        for name in names:
            source = (ROOT / "bitrix_connector" / name).read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, source, (name, value))


if __name__ == "__main__":
    unittest.main()
