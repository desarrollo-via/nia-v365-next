import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_existing_diagnostic_gate import (
    PreparedExistingHistoryDiagnosticGate,
    compose_prepared_existing_history_diagnostic_gate,
    preview_prepared_existing_history_diagnostic_gate,
)


ROOT = Path(__file__).resolve().parents[1]


class ExistingHistoryDiagnosticGateTests(unittest.TestCase):
    def test_default_snapshot_is_prepared_but_has_no_authorization(self):
        snapshot = preview_prepared_existing_history_diagnostic_gate()

        self.assertEqual(snapshot.phase, "M49")
        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(
            snapshot.reason,
            "bitrix_history_existing_gate_awaiting_separate_authorization",
        )
        self.assertTrue(snapshot.adapter_composer_bound)
        self.assertTrue(snapshot.authorization_required)
        self.assertFalse(snapshot.authorization_present)
        self.assertFalse(snapshot.authorization_phrase_defined)
        self.assertFalse(snapshot.authorization_reusable)
        self.assertFalse(snapshot.source_bound)
        self.assertFalse(snapshot.cli_available)
        self.assertFalse(snapshot.command_available)
        self.assertFalse(snapshot.real_execution_authorized)
        self.assertFalse(snapshot.source_open_authorized)
        self.assertFalse(snapshot.oauth_refresh_authorized)
        self.assertFalse(snapshot.retry_authorized)
        self.assertFalse(snapshot.human_message_required)
        self.assertFalse(snapshot.waiting_message_allowed)
        self.assertEqual(snapshot.dialog_read_budget, 1)
        self.assertEqual(snapshot.history_read_budget, 1)

    def test_all_operational_counters_and_effects_stay_zero(self):
        snapshot = preview_prepared_existing_history_diagnostic_gate()

        for field in (
            "adapter_composer_calls",
            "adapter_execute_calls",
            "dialog_read_calls",
            "history_read_calls",
            "wait_calls",
            "message_requests",
            "mutation_calls",
            "external_calls",
        ):
            self.assertEqual(getattr(snapshot, field), 0, field)
        self.assertTrue(snapshot.connector_locked_off)
        self.assertFalse(snapshot.persisted)
        self.assertFalse(snapshot.nia_called)
        self.assertFalse(snapshot.bitrix_written)

    def test_injected_adapter_spy_is_bound_but_never_called(self):
        calls = []

        def adapter_spy(*_args, **_kwargs):
            calls.append(True)
            raise AssertionError("adapter must not run")

        snapshot = preview_prepared_existing_history_diagnostic_gate(
            compose_gate=lambda: compose_prepared_existing_history_diagnostic_gate(
                adapter_composer=adapter_spy
            )
        )

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(calls, [])

    def test_gate_is_redacted_non_callable_and_has_no_execute_method(self):
        gate = compose_prepared_existing_history_diagnostic_gate()

        self.assertIs(type(gate), PreparedExistingHistoryDiagnosticGate)
        self.assertEqual(
            repr(gate),
            "PreparedExistingHistoryDiagnosticGate(<redacted>)",
        )
        self.assertFalse(callable(gate))
        self.assertFalse(hasattr(gate, "execute"))

    def test_invalid_dependency_or_gate_fails_closed(self):
        invalid_dependency = preview_prepared_existing_history_diagnostic_gate(
            compose_gate=lambda: compose_prepared_existing_history_diagnostic_gate(
                adapter_composer=None
            )
        )
        invalid_gate = preview_prepared_existing_history_diagnostic_gate(
            compose_gate=lambda: object()
        )

        self.assertEqual(invalid_dependency.state, "NO-GO")
        self.assertEqual(invalid_gate.state, "NO-GO")
        self.assertFalse(invalid_dependency.real_execution_authorized)
        self.assertFalse(invalid_gate.real_execution_authorized)
        self.assertEqual(invalid_dependency.external_calls, 0)
        self.assertEqual(invalid_gate.external_calls, 0)

    def test_source_has_no_phrase_source_cli_wait_or_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_existing_diagnostic_gate.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            ".open(",
            "dotenv",
            "os.environ",
            "get_access_token(",
            "refresh_access_token(",
            "get_dialog(",
            "get_session_history(",
            "sleep(",
            "waiting-message",
            "send_message",
            "input(",
            "asyncio.run",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "execute=true",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
