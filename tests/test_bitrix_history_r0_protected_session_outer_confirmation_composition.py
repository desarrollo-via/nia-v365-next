import asyncio
import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_builder_composition import (
    DormantProtectedSessionBuilderCompositionSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_session_outer_confirmation_composition import (
    InjectedOuterHumanConfirmation,
    OUTER_CONFIRMATION_SCOPE,
    prepare_dormant_protected_session_outer_confirmation,
)


ROOT = Path(__file__).resolve().parents[1]


def prepared_builder_contract():
    return DormantProtectedSessionBuilderCompositionSnapshot(
        state="PREPARED",
        reason="fictional-m29-builder-contract",
        parser_contract_consumed=True,
        path_builder_bound=True,
        source_builder_bound=True,
        private_builder_bound=True,
    )


class ProtectedSessionOuterConfirmationCompositionTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_default_is_dormant_and_does_not_read_confirmation(self):
        calls = 0

        async def reader():
            nonlocal calls
            calls += 1
            raise AssertionError("dormant boundary must not read")

        result = await prepare_dormant_protected_session_outer_confirmation(
            builder_contract=prepared_builder_contract(),
            confirmation_reader=reader,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(
            result.reason,
            "protected_history_session_outer_confirmation_dormant_default",
        )
        self.assertEqual(calls, 0)
        self.assertEqual(result.confirmation_calls, 0)
        self.assertFalse(result.command_available)

    async def test_injected_double_prepares_exactly_once_but_enables_nothing(self):
        calls = 0

        async def reader():
            nonlocal calls
            calls += 1
            return InjectedOuterHumanConfirmation(
                approved=True, scope=OUTER_CONFIRMATION_SCOPE
            )

        result = await prepare_dormant_protected_session_outer_confirmation(
            builder_contract=prepared_builder_contract(),
            activation_requested=True,
            confirmation_reader=reader,
        )
        self.assertEqual(result.state, "PREPARED")
        self.assertEqual(calls, 1)
        self.assertEqual(result.confirmation_attempt_limit, 1)
        self.assertEqual(result.confirmation_calls, 1)
        self.assertEqual(result.confirmation_timeout_seconds, 300)
        self.assertTrue(result.confirmation_verified)
        self.assertTrue(result.human_boundary_prepared)
        for field in (
            "builder_calls", "source_calls", "materializer_calls", "external_calls"
        ):
            self.assertEqual(getattr(result, field), 0, field)
        for field in (
            "parser_real_enabled", "builder_real_enabled", "command_available",
            "source_open_authorized", "real_execution_authorized",
            "message_request_authorized",
        ):
            self.assertFalse(getattr(result, field), field)

    async def test_timeout_runner_receives_absolute_300_and_fails_terminal(self):
        seen = []

        async def reader():
            return InjectedOuterHumanConfirmation(
                approved=True, scope=OUTER_CONFIRMATION_SCOPE
            )

        async def timeout_runner(awaitable, *, timeout):
            seen.append(timeout)
            awaitable.close()
            raise asyncio.TimeoutError

        result = await prepare_dormant_protected_session_outer_confirmation(
            builder_contract=prepared_builder_contract(),
            activation_requested=True,
            confirmation_reader=reader,
            timeout_runner=timeout_runner,
        )
        self.assertEqual(seen, [300.0])
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(
            result.reason,
            "protected_history_session_outer_confirmation_timeout_terminal",
        )
        self.assertEqual(result.confirmation_calls, 1)

    async def test_cancellation_is_terminal_and_normalized(self):
        async def reader():
            raise asyncio.CancelledError

        result = await prepare_dormant_protected_session_outer_confirmation(
            builder_contract=prepared_builder_contract(),
            activation_requested=True,
            confirmation_reader=reader,
        )
        self.assertEqual(result.state, "CANCELLED")
        self.assertEqual(result.confirmation_calls, 1)
        self.assertFalse(result.human_boundary_prepared)

    async def test_rejected_confirmation_fails_closed(self):
        async def reader():
            return InjectedOuterHumanConfirmation(approved=True, scope="wrong")

        result = await prepare_dormant_protected_session_outer_confirmation(
            builder_contract=prepared_builder_contract(),
            activation_requested=True,
            confirmation_reader=reader,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.confirmation_calls, 1)
        self.assertFalse(result.confirmation_verified)

    async def test_degraded_m28_contract_is_rejected_before_reader(self):
        calls = 0

        async def reader():
            nonlocal calls
            calls += 1
            return InjectedOuterHumanConfirmation(
                approved=True, scope=OUTER_CONFIRMATION_SCOPE
            )

        degraded = replace(prepared_builder_contract(), command_available=True)
        result = await prepare_dormant_protected_session_outer_confirmation(
            builder_contract=degraded,
            activation_requested=True,
            confirmation_reader=reader,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(calls, 0)
        self.assertFalse(result.builder_contract_consumed)

    def test_source_has_no_secret_source_external_or_interactive_surface(self):
        source = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_session_outer_confirmation_composition.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "Path(", "open(", ".env", "load_dotenv", "os.environ",
            "get_access_token", "refresh_access_token", "get_dialog(",
            "get_session_history(", "httpx", "pymongo", "subprocess", "socket",
            "argparse", "input(", "asyncio.run", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
