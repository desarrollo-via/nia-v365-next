import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m79_real_substitution_audit import (
    M79_REAL_SUBSTITUTIONS,
    audit_m79_real_substitutions,
)


ROOT = Path(__file__).resolve().parents[1]


class M79RealSubstitutionAuditTests(unittest.TestCase):
    def test_exact_six_real_substitutions_are_mapped_once(self):
        audit = audit_m79_real_substitutions()
        self.assertEqual(audit.substitutions, M79_REAL_SUBSTITUTIONS)
        self.assertEqual(len(audit.substitutions), 6)
        self.assertEqual(len({item.boundary for item in audit.substitutions}), 6)
        self.assertTrue(all(not item.ready for item in audit.substitutions))

    def test_complete_required_chain_is_reaudited(self):
        self.assertEqual(
            audit_m79_real_substitutions().audited_chain,
            ("M63", "M68", "M73", "M75", "M76", "M77", "M78"),
        )

    def test_public_object_ids_and_window_are_exact(self):
        package = audit_m79_real_substitutions().package
        self.assertEqual(
            (package.target_chat_id, package.target_dialog_id, package.target_line_id,
             package.controlled_bot_id, package.production_bot_id,
             package.maximum_window_seconds),
            (78733, "chat78733", 13, 373259, 245339, 180),
        )

    def test_budgets_are_closed_and_retry_and_refresh_are_zero(self):
        package = audit_m79_real_substitutions().package
        self.assertTrue(all(value == 0 for _, value in package.mutation_budgets))
        budgets = dict(package.read_and_call_budgets)
        self.assertEqual((budgets["oauth_refresh"], budgets["retry"]), (0, 0))
        self.assertTrue(all(value == 1 for key, value in budgets.items() if key not in {"oauth_refresh", "retry"}))

    def test_stop_evidence_and_exact_rollback_are_present(self):
        package = audit_m79_real_substitutions().package
        self.assertIn("preflight_drift_or_ambiguity", package.stop_criteria)
        self.assertIn("only_chat78733_reached_nia_next", package.required_evidence)
        self.assertIn("exact_send_receipt_message_id", package.exact_rollback)
        self.assertIn("same_session_history_read_verifying_absence", package.exact_rollback)

    def test_contradiction_is_visible_without_being_corrected(self):
        contradiction = audit_m79_real_substitutions().package.contradiction
        self.assertIn("m63_first_literal_names_local_dotenv", contradiction)
        self.assertIn("forbids_opening_or_reading_dotenv", contradiction)

    def test_package_is_redacted_and_not_requestable(self):
        package = audit_m79_real_substitutions().package
        self.assertEqual((package.state, package.decision), ("NO-GO", "DO-NOT-REQUEST"))
        self.assertTrue(package.package_redacted)
        self.assertFalse(package.confirmation_text_included)
        for field in (
            "first_confirmation_request_ready", "attention_required_now",
            "human_message_required_now", "source_bound", "command_available",
            "real_execution_authorized", "persisted", "nia_next_called",
            "bitrix_written",
        ):
            self.assertFalse(getattr(package, field), field)
        self.assertEqual(package.external_calls, 0)
        self.assertTrue(package.connector_locked_off)

    def test_invalid_ledger_is_rejected(self):
        audit = audit_m79_real_substitutions()
        with self.assertRaises(ValueError):
            replace(audit, substitutions=audit.substitutions[:-1])

    def test_source_has_no_io_secrets_clients_commands_or_attention_effect(self):
        source = (ROOT / "bitrix_connector" / "bitrix_history_r0_m79_real_substitution_audit.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "open(", "httpx", "pymongo", "argparse", "input(", "subprocess",
            "socket", "get_access_token(", "refresh_access_token(", "print(",
            "toast", "messagebox", "async def", "os.environ", "dotenv_values",
            "client_secret", "access_token",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
