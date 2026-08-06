import asyncio
import unittest
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
    PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
    compose_protected_history_session_execution_gate,
)
from bitrix_connector.bitrix_history_r0_protected_session_gate_owner import (
    ProtectedHistorySessionGateOwnerSnapshot,
    execute_materialized_history_session_gate_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_human_boundary_contract import (
    PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT,
)
from bitrix_connector.bitrix_history_r0_protected_session_plan_materializer import (
    materialize_private_protected_history_session_plan_once,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("M22 audit must not build resources")


def coordinator_result(state="RECEIVED"):
    return ProtectedHistorySessionCoordinatorSnapshot(
        state=state,
        reason="fictional-m22-coordinator",
        execution_requested=True,
        launcher_compositions=1,
        adapter_compositions=1,
        entrypoint_calls=1,
        private_state_cleared=True,
    )


def materialized(coordinator):
    def gate_composer(*, plan):
        return compose_protected_history_session_execution_gate(
            plan=plan, coordinator=coordinator
        )

    return materialize_private_protected_history_session_plan_once(
        dotenv_path=Path("fictional-m22.env"),
        inputs=BitrixHistoryR0EphemeralInputs(
            expected_text_sha256="e" * 64,
            window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        resources_factory=FakeResourcesFactory(),
        preflight_client_builder=lambda **_kwargs: object(),
        reader_client_builder=lambda **_kwargs: object(),
        confirmation_reader=lambda: asyncio.sleep(0, result="fictional-inner"),
        gate_composer=gate_composer,
    )


class ProtectedSessionHumanBoundaryAuditTests(unittest.IsolatedAsyncioTestCase):
    def test_contract_freezes_limits_barriers_and_no_real_authority(self):
        contract = PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT

        self.assertEqual(contract.phase, "M22")
        self.assertEqual(contract.owner_call_limit, 1)
        self.assertEqual(contract.confirmation_read_limit, 1)
        self.assertEqual(contract.confirmation_timeout_seconds, 300)
        self.assertTrue(contract.literal_confirmation_required)
        self.assertTrue(contract.timeout_terminal)
        self.assertTrue(contract.cancellation_terminal)
        self.assertTrue(contract.cleanup_required)
        self.assertTrue(contract.connector_locked_off)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_called)
        self.assertFalse(contract.bitrix_written)
        self.assertFalse(contract.real_source_configured)
        self.assertFalse(contract.real_execution_authorized)
        self.assertFalse(contract.message_request_authorized)

    async def test_success_crosses_m20_m21_once_and_cleans(self):
        calls = {"coordinator": 0, "confirmation": 0}

        async def coordinator(**_kwargs):
            calls["coordinator"] += 1
            return coordinator_result()

        async def confirmation():
            calls["confirmation"] += 1
            return PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION

        owner = materialized(coordinator)
        result = await execute_materialized_history_session_gate_once(
            materialized=owner, confirmation_reader=confirmation
        )

        self.assertEqual(result.state, "RECEIVED")
        self.assertEqual(calls, {"coordinator": 1, "confirmation": 1})
        self.assertEqual(owner.snapshot().state, "CLEARED")

    async def test_rejection_stops_before_coordinator_and_cleans(self):
        coordinator_calls = 0

        async def coordinator(**_kwargs):
            nonlocal coordinator_calls
            coordinator_calls += 1
            return coordinator_result()

        owner = materialized(coordinator)
        result = await execute_materialized_history_session_gate_once(
            materialized=owner,
            confirmation_reader=lambda: asyncio.sleep(0, result="NO AUTORIZADO"),
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(coordinator_calls, 0)
        self.assertEqual(owner.snapshot().state, "CLEARED")

    async def test_outer_timeout_is_terminal_and_cleans(self):
        owner = materialized(
            lambda **_kwargs: asyncio.sleep(0, result=coordinator_result())
        )

        async def blocked_confirmation():
            await asyncio.Event().wait()

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                execute_materialized_history_session_gate_once(
                    materialized=owner, confirmation_reader=blocked_confirmation
                ),
                timeout=0.01,
            )
        self.assertEqual(owner.snapshot().state, "CLEARED")
        self.assertEqual(owner.snapshot().cleanup_calls, 1)

    async def test_human_cancellation_is_terminal_and_cleans(self):
        owner = materialized(
            lambda **_kwargs: asyncio.sleep(0, result=coordinator_result())
        )

        async def cancelled_confirmation():
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await execute_materialized_history_session_gate_once(
                materialized=owner, confirmation_reader=cancelled_confirmation
            )
        self.assertEqual(owner.snapshot().state, "CLEARED")
        self.assertEqual(owner.snapshot().cleanup_calls, 1)

    async def test_failure_is_redacted_allowlisted_and_cleans(self):
        owner = materialized(
            lambda **_kwargs: asyncio.sleep(0, result=coordinator_result())
        )

        async def failed_confirmation():
            raise RuntimeError("fictional-m22-private-human-detail")

        result = await execute_materialized_history_session_gate_once(
            materialized=owner, confirmation_reader=failed_confirmation
        )
        payload = asdict(result)
        contract = PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT

        self.assertEqual(tuple(payload), contract.allowed_output_fields)
        self.assertIn(result.state, contract.allowed_states)
        self.assertIn(result.reason, contract.allowed_reasons)
        self.assertNotIn("private-human", repr(payload))
        self.assertEqual(owner.snapshot().state, "CLEARED")

    def test_contract_and_owner_sources_have_no_real_or_interactive_surface(self):
        names = (
            "bitrix_history_r0_protected_session_human_boundary_contract.py",
            "bitrix_history_r0_protected_session_gate_owner.py",
        )
        forbidden = (
            "open(", "os.environ", "load_dotenv", "get_access_token",
            "refresh_access_token", "get_dialog(", "get_session_history(",
            "httpx", "pymongo", "subprocess", "socket", "argparse", "input(",
        )
        for name in names:
            source = (ROOT / "bitrix_connector" / name).read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, source, (name, value))

        serialized = repr(asdict(PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT))
        for private in (
            "chat78733", "78733", "614949", "373259", "245339",
            "member_id", "expected_text", "dotenv_path",
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
        ):
            self.assertNotIn(private, serialized)


if __name__ == "__main__":
    unittest.main()
