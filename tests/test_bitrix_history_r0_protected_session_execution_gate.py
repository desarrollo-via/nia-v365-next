import asyncio
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
    ProtectedHistorySessionExecutionPlan,
)
from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
    PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
    PreparedProtectedHistorySessionExecutionGate,
    compose_protected_history_session_execution_gate,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("resources must not run in M17")


def execution_plan():
    return ProtectedHistorySessionExecutionPlan(
        dotenv_path=Path("fictional-m17.env"),
        inputs=BitrixHistoryR0EphemeralInputs(
            expected_text_sha256="c" * 64,
            window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        resources_factory=FakeResourcesFactory(),
        preflight_client_builder=lambda **_kwargs: object(),
        reader_client_builder=lambda **_kwargs: object(),
        confirmation_reader=lambda: asyncio.sleep(0, result="fictional-m17-inner"),
    )


def received_snapshot(**changes):
    values = {
        "state": "RECEIVED",
        "reason": "protected_history_session_coordinator_received",
        "execution_requested": True,
        "launcher_compositions": 1,
        "adapter_compositions": 1,
        "entrypoint_calls": 1,
        "owner_builder_calls": 1,
        "settings_capture_calls": 1,
        "confirmation_calls": 1,
        "reader_factory_calls": 1,
        "reader_calls": 1,
        "cleanup_calls": 1,
        "private_state_cleared": True,
    }
    values.update(changes)
    return ProtectedHistorySessionCoordinatorSnapshot(**values)


class ProtectedSessionExecutionGateTests(unittest.IsolatedAsyncioTestCase):
    def test_composition_is_inert_and_redacted(self):
        calls = 0

        async def coordinator(**_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("coordinator must not run")

        gate = compose_protected_history_session_execution_gate(
            plan=execution_plan(), coordinator=coordinator
        )

        self.assertIsInstance(gate, PreparedProtectedHistorySessionExecutionGate)
        self.assertEqual(
            repr(gate), "PreparedProtectedHistorySessionExecutionGate(<redacted>)"
        )
        self.assertEqual(gate.snapshot().state, "PREPARED")
        self.assertEqual(gate.snapshot().gate_attempts, 0)
        self.assertEqual(gate.snapshot().coordinator_calls, 0)
        self.assertEqual(calls, 0)

    async def test_exact_phrase_calls_coordinator_once_and_normalizes(self):
        calls = []
        plan = execution_plan()

        async def coordinator(**kwargs):
            calls.append(kwargs)
            return received_snapshot()

        gate = compose_protected_history_session_execution_gate(
            plan=plan, coordinator=coordinator
        )
        result = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(result.state, "RECEIVED")
        self.assertEqual(result.gate_attempts, 1)
        self.assertEqual(result.coordinator_calls, 1)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]["plan"], plan)
        self.assertIs(calls[0]["execute"], True)
        self.assertTrue(result.private_state_cleared)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_called)
        self.assertFalse(result.bitrix_written)

    async def test_wrong_phrase_consumes_attempt_before_coordinator(self):
        calls = 0

        async def coordinator(**_kwargs):
            nonlocal calls
            calls += 1
            return received_snapshot()

        gate = compose_protected_history_session_execution_gate(
            plan=execution_plan(), coordinator=coordinator
        )
        result = await gate.execute_once("NO AUTORIZADO")

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(
            result.reason, "protected_history_session_execution_gate_rejected"
        )
        self.assertEqual(result.gate_attempts, 1)
        self.assertEqual(result.coordinator_calls, 0)
        self.assertEqual(calls, 0)
        self.assertNotIn("NO AUTORIZADO", repr(asdict(result)))

    async def test_second_call_never_retries_after_success(self):
        calls = 0

        async def coordinator(**_kwargs):
            nonlocal calls
            calls += 1
            return received_snapshot()

        gate = compose_protected_history_session_execution_gate(
            plan=execution_plan(), coordinator=coordinator
        )
        first = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )
        second = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(first.state, "RECEIVED")
        self.assertEqual(second.state, "NO-GO")
        self.assertEqual(
            second.reason, "protected_history_session_execution_gate_already_used"
        )
        self.assertEqual(second.coordinator_calls, 1)
        self.assertEqual(calls, 1)

    async def test_degraded_barrier_is_terminal_and_redacted(self):
        async def coordinator(**_kwargs):
            return received_snapshot(bitrix_written=True)

        gate = compose_protected_history_session_execution_gate(
            plan=execution_plan(), coordinator=coordinator
        )
        result = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(
            result.reason, "protected_history_session_execution_gate_failed_safe"
        )
        self.assertFalse(result.bitrix_written)
        self.assertEqual(result.coordinator_calls, 1)

    async def test_coordinator_failure_is_redacted_without_retry(self):
        private_detail = "fictional-m17-private-coordinator-detail"
        calls = 0

        async def coordinator(**_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError(private_detail)

        gate = compose_protected_history_session_execution_gate(
            plan=execution_plan(), coordinator=coordinator
        )
        result = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )
        retry = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.coordinator_calls, 1)
        self.assertEqual(retry.state, "NO-GO")
        self.assertEqual(calls, 1)
        self.assertNotIn(private_detail, repr(asdict(result)))

    async def test_cancellation_reraises_and_attempt_stays_consumed(self):
        calls = 0

        async def coordinator(**_kwargs):
            nonlocal calls
            calls += 1
            raise asyncio.CancelledError

        gate = compose_protected_history_session_execution_gate(
            plan=execution_plan(), coordinator=coordinator
        )
        with self.assertRaises(asyncio.CancelledError):
            await gate.execute_once(PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION)
        retry = await gate.execute_once(
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
        )

        self.assertEqual(retry.state, "NO-GO")
        self.assertEqual(retry.coordinator_calls, 1)
        self.assertEqual(calls, 1)

    def test_missing_or_invalid_plan_is_rejected_without_coordinator(self):
        with self.assertRaisesRegex(
            TypeError, "protected_history_session_execution_gate_dependency_invalid"
        ):
            compose_protected_history_session_execution_gate(plan=None)

    def test_source_has_no_direct_external_or_interactive_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_execution_gate.py"
        ).read_text(encoding="utf-8")
        self.assertIn(PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION, source)
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
