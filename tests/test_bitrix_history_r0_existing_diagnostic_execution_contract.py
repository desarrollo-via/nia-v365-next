import unittest
from pathlib import Path

from pydantic import ValidationError

from bitrix_connector.bitrix_history_r0_existing_diagnostic_execution_contract import (
    EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT,
    ExistingHistoryDiagnosticExecutionContract,
)


ROOT = Path(__file__).resolve().parents[1]


class ExistingHistoryDiagnosticExecutionContractTests(unittest.TestCase):
    def test_contract_is_prepared_but_has_no_usable_authorization(self):
        contract = EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT

        self.assertEqual(contract.phase, "M50")
        self.assertEqual(contract.state, "PREPARED")
        self.assertTrue(contract.separate_exact_authorization_required)
        self.assertFalse(contract.authorization_present)
        self.assertFalse(contract.authorization_phrase_defined)
        self.assertTrue(contract.authorization_consumed_on_attempt)
        self.assertFalse(contract.authorization_reusable)
        self.assertFalse(contract.command_available)
        self.assertFalse(contract.cli_available)
        self.assertFalse(contract.source_bound)
        self.assertFalse(contract.real_execution_authorized)
        self.assertFalse(contract.source_open_authorized)
        self.assertFalse(contract.bitrix_reads_authorized)

    def test_scope_is_only_shape_diagnosis_and_not_receipt(self):
        contract = EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT

        self.assertTrue(contract.objective_existing_history_shape_only)
        self.assertFalse(contract.authentic_receipt_proven_by_this_contract)
        self.assertFalse(contract.checklist_38_completion_authorized)
        self.assertFalse(contract.human_message_required)
        self.assertFalse(contract.waiting_message_allowed)
        self.assertEqual(contract.dialog_read_budget, 1)
        self.assertEqual(contract.history_read_budget, 1)
        self.assertEqual(contract.message_send_budget, 0)
        self.assertEqual(contract.wait_budget, 0)

    def test_preconditions_and_terminal_stops_are_explicit(self):
        contract = EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT

        for field in (
            "connector_barriers_required",
            "protected_source_required",
            "preflight_ready_required",
            "resources_closed_required",
            "no_oauth_refresh",
            "no_retry",
            "stop_on_authorization_invalid",
            "stop_on_barrier_degraded",
            "stop_on_source_or_oauth_failure",
            "stop_on_preflight_failure",
            "stop_on_history_failure",
            "stop_on_close_failure",
            "stop_on_ambiguous_output",
        ):
            self.assertTrue(getattr(contract, field), field)

    def test_output_is_allowlisted_and_private_surfaces_are_false(self):
        contract = EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT

        for field in (
            "output_status_only",
            "output_safe_reason_only",
            "output_m44_category_only",
            "output_counters_only",
            "output_barriers_only",
        ):
            self.assertTrue(getattr(contract, field), field)
        for field in (
            "output_message_content",
            "output_session_identity",
            "output_external_body",
            "output_credentials",
        ):
            self.assertFalse(getattr(contract, field), field)

    def test_contract_is_frozen_strict_and_keeps_every_effect_zero(self):
        contract = EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT

        for field in (
            "dialog_read_calls",
            "history_read_calls",
            "mutation_calls",
            "external_calls",
        ):
            self.assertEqual(getattr(contract, field), 0, field)
        self.assertTrue(contract.connector_locked_off)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_called)
        self.assertFalse(contract.bitrix_written)
        with self.assertRaises(ValidationError):
            ExistingHistoryDiagnosticExecutionContract(extra_field=True)
        with self.assertRaises(ValidationError):
            ExistingHistoryDiagnosticExecutionContract(dialog_read_calls=1)

    def test_source_has_no_phrase_command_source_or_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_existing_diagnostic_execution_contract.py"
        ).read_text(encoding="utf-8").lower()
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
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
