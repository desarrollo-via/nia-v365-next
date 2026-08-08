import asyncio
import unittest
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
    execute_materialized_history_session_gate_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_plan_materializer import (
    materialize_private_protected_history_session_plan_once,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("resources must not run")


def coordinator_result(state="RECEIVED", **changes):
    values = {
        "state": state,
        "reason": "fictional-m21-coordinator",
        "execution_requested": True,
        "launcher_compositions": 1,
        "adapter_compositions": 1,
        "entrypoint_calls": 1,
        "private_state_cleared": True,
    }
    values.update(changes)
    return ProtectedHistorySessionCoordinatorSnapshot(**values)


def materialized(coordinator):
    def gate_composer(*, plan):
        return compose_protected_history_session_execution_gate(
            plan=plan, coordinator=coordinator
        )

    return materialize_private_protected_history_session_plan_once(
        dotenv_path=Path("fictional-m21.env"),
        inputs=BitrixHistoryR0EphemeralInputs(
            expected_text_sha256="f" * 64,
            window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        resources_factory=FakeResourcesFactory(),
        preflight_client_builder=lambda **_kwargs: object(),
        reader_client_builder=lambda **_kwargs: object(),
        confirmation_reader=lambda: asyncio.sleep(0, result="fictional-inner"),
        gate_composer=gate_composer,
    )


class ProtectedSessionGateOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_confirmation_consumes_gate_once_and_cleans(self):
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
        self.assertEqual(result.take_calls, 1)
        self.assertEqual(result.confirmation_calls, 1)
        self.assertEqual(result.gate_calls, 1)
        self.assertEqual(result.cleanup_calls, 1)
        self.assertEqual(calls, {"coordinator": 1, "confirmation": 1})
        self.assertEqual(owner.snapshot().state, "CLEARED")
        self.assertFalse(owner.snapshot().plan_retained)
        self.assertFalse(owner.snapshot().gate_retained)

    async def test_wrong_confirmation_never_reaches_coordinator_and_cleans(self):
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
        self.assertEqual(result.gate_calls, 1)
        self.assertEqual(coordinator_calls, 0)
        self.assertEqual(owner.snapshot().state, "CLEARED")

    async def test_second_owner_call_stops_before_confirmation(self):
        confirmation_calls = 0

        async def coordinator(**_kwargs):
            return coordinator_result()

        async def confirmation():
            nonlocal confirmation_calls
            confirmation_calls += 1
            return PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION

        owner = materialized(coordinator)
        first = await execute_materialized_history_session_gate_once(
            materialized=owner, confirmation_reader=confirmation
        )
        second = await execute_materialized_history_session_gate_once(
            materialized=owner, confirmation_reader=confirmation
        )

        self.assertEqual(first.state, "RECEIVED")
        self.assertEqual(second.state, "NO-GO")
        self.assertEqual(second.confirmation_calls, 0)
        self.assertEqual(confirmation_calls, 1)

    async def test_confirmation_failure_is_redacted_and_cleans(self):
        owner = materialized(lambda **_kwargs: asyncio.sleep(0, result=coordinator_result()))

        async def confirmation():
            raise RuntimeError("fictional-m21-private-confirmation-detail")

        result = await execute_materialized_history_session_gate_once(
            materialized=owner, confirmation_reader=confirmation
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertNotIn("private-confirmation", repr(result))
        self.assertEqual(result.cleanup_calls, 1)
        self.assertEqual(owner.snapshot().state, "CLEARED")

    async def test_cancellation_reraises_and_cleans(self):
        owner = materialized(lambda **_kwargs: asyncio.sleep(0, result=coordinator_result()))

        async def confirmation():
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await execute_materialized_history_session_gate_once(
                materialized=owner, confirmation_reader=confirmation
            )
        self.assertEqual(owner.snapshot().state, "CLEARED")

    async def test_degraded_result_fails_closed(self):
        async def coordinator(**_kwargs):
            return coordinator_result(bitrix_written=True)

        owner = materialized(coordinator)
        result = await execute_materialized_history_session_gate_once(
            materialized=owner,
            confirmation_reader=lambda: asyncio.sleep(
                0, result=PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
            ),
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertFalse(result.bitrix_written)
        self.assertEqual(owner.snapshot().state, "CLEARED")

    def test_source_has_no_direct_external_or_interactive_surfaces(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_protected_session_gate_owner.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "os.environ", "load_dotenv", "get_access_token",
            "refresh_access_token", "get_dialog(", "get_session_history(",
            "httpx", "pymongo", "subprocess", "socket", "argparse", "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
