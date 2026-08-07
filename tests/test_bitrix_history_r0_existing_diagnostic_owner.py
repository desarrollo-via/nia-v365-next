import inspect
import unittest

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
    BitrixSessionHistory,
)
from bitrix_connector.bitrix_history_r0_existing_diagnostic_owner import (
    ExistingHistoryDiagnosticState,
    execute_existing_history_diagnostic_once,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings


def settings():
    return load_settings({"NIA_BITRIX_MODE": "off"})


def ready_preflight():
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
        BitrixHistoryR0Anchor(session_id=900, baseline_last_message_id=100),
    )


class FakeHistoryReader:
    def __init__(self, result, *, close_error=False):
        self.result = result
        self.close_error = close_error
        self.calls = []
        self.closed = False

    async def get_session_history(self, session_id):
        self.calls.append(session_id)
        return self.result

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("private close detail")


class ExistingHistoryDiagnosticOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_is_prepared_and_performs_no_calls(self):
        calls = []

        async def preflight(_settings):
            calls.append("preflight")

        async def factory():
            calls.append("factory")

        result = await execute_existing_history_diagnostic_once(
            execute=False,
            settings=settings(),
            preflight_executor=preflight,
            history_reader_factory=factory,
        )

        self.assertEqual(result.state, ExistingHistoryDiagnosticState.PREPARED)
        self.assertEqual(calls, [])
        self.assertTrue(result.resources_closed)
        self.assertEqual(result.dialog_read_calls, 0)
        self.assertEqual(result.history_read_calls, 0)

    async def test_executes_one_preflight_and_one_existing_history_read(self):
        preflight_calls = []
        history = BitrixSessionHistory.model_validate(
            {
                "chatId": 78733,
                "sessionId": 900,
                "message": [],
                "users": [],
            }
        )
        reader = FakeHistoryReader(
            BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.SUCCESS,
                history=history,
            )
        )

        async def preflight(value):
            preflight_calls.append(value)
            return ready_preflight()

        async def factory():
            return reader

        result = await execute_existing_history_diagnostic_once(
            execute=True,
            settings=settings(),
            preflight_executor=preflight,
            history_reader_factory=factory,
        )

        self.assertEqual(result.state, ExistingHistoryDiagnosticState.DIAGNOSED)
        self.assertEqual(result.reason, "bitrix_history_existing_contract_valid")
        self.assertEqual(len(preflight_calls), 1)
        self.assertEqual(reader.calls, [900])
        self.assertTrue(reader.closed)
        self.assertEqual(result.dialog_read_calls, 1)
        self.assertEqual(result.history_read_calls, 1)
        self.assertNotIn("session", result.model_dump_json())
        self.assertNotIn("message", result.model_dump_json())

    async def test_preflight_no_go_prevents_history_factory(self):
        factory_calls = []

        async def preflight(_settings):
            return BitrixHistoryR0PreflightOutcome(
                BitrixHistoryR0Result(
                    status=BitrixHistoryR0Status.NO_GO,
                    reason="bitrix_history_dialog_mismatch",
                    dialog_read_calls=1,
                    history_read_calls=0,
                    resources_closed=True,
                )
            )

        async def factory():
            factory_calls.append(True)

        result = await execute_existing_history_diagnostic_once(
            execute=True,
            settings=settings(),
            preflight_executor=preflight,
            history_reader_factory=factory,
        )

        self.assertEqual(result.state, ExistingHistoryDiagnosticState.NO_GO)
        self.assertEqual(result.failure_category, "reader_dialog_mismatch")
        self.assertEqual(factory_calls, [])
        self.assertEqual(result.history_read_calls, 0)

    async def test_three_structural_history_failures_are_preserved_and_redacted(self):
        cases = (
            ("bitrix_history_invalid_envelope", "reader_history_envelope_invalid"),
            ("bitrix_history_invalid_collections", "reader_history_collections_invalid"),
            ("bitrix_history_invalid_fields", "reader_history_fields_invalid"),
        )
        for reason, category in cases:
            with self.subTest(reason=reason):
                reader = FakeHistoryReader(
                    BitrixHistoryReadResult(
                        decision=BitrixHistoryReadDecision.FAIL,
                        error_code=reason,
                    )
                )

                async def preflight(_settings):
                    return ready_preflight()

                async def factory():
                    return reader

                result = await execute_existing_history_diagnostic_once(
                    execute=True,
                    settings=settings(),
                    preflight_executor=preflight,
                    history_reader_factory=factory,
                )

                self.assertEqual(result.state, ExistingHistoryDiagnosticState.NO_GO)
                self.assertEqual(result.failure_category, category)
                self.assertEqual(result.history_read_calls, 1)
                self.assertTrue(reader.closed)
                self.assertNotIn("private", result.model_dump_json())

    async def test_errors_and_close_failure_fail_closed_without_details(self):
        async def preflight(_settings):
            return ready_preflight()

        async def failing_factory():
            raise RuntimeError("private factory detail")

        factory_result = await execute_existing_history_diagnostic_once(
            execute=True,
            settings=settings(),
            preflight_executor=preflight,
            history_reader_factory=failing_factory,
        )
        self.assertEqual(factory_result.state, ExistingHistoryDiagnosticState.NO_GO)
        self.assertEqual(factory_result.failure_category, "reader_history_unavailable")
        self.assertEqual(factory_result.history_read_calls, 0)
        self.assertNotIn("private", factory_result.model_dump_json())

        reader = FakeHistoryReader(
            BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.FAIL,
                error_code="bitrix_history_invalid_response",
            ),
            close_error=True,
        )

        async def close_factory():
            return reader

        close_result = await execute_existing_history_diagnostic_once(
            execute=True,
            settings=settings(),
            preflight_executor=preflight,
            history_reader_factory=close_factory,
        )
        self.assertEqual(close_result.failure_category, "reader_resources_close_failed")
        self.assertFalse(close_result.resources_closed)
        self.assertNotIn("private", close_result.model_dump_json())

    def test_source_has_no_wait_poll_message_or_runtime_composition(self):
        source = inspect.getsource(execute_existing_history_diagnostic_once).lower()
        for forbidden in (
            "sleep(",
            "waiting-message",
            "send_message",
            "oauth",
            "httpx",
            "dotenv",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
