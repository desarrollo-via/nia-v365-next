import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m67_operational_audit import (
    M67_MISSING_OPERATIONAL_LINKS,
    M67OperationalAudit,
    audit_m62_m66_operational_readiness,
)


ROOT = Path(__file__).resolve().parents[1]


class M67OperationalAuditTests(unittest.TestCase):
    def test_decision_is_no_go_with_exact_nine_missing_links(self):
        audit = audit_m62_m66_operational_readiness()

        self.assertEqual(audit.phase, "M67")
        self.assertEqual(audit.state, "NO-GO")
        self.assertEqual(audit.missing_operational_link_count, 9)
        self.assertEqual(audit.missing_operational_links, M67_MISSING_OPERATIONAL_LINKS)
        self.assertEqual(len(set(audit.missing_operational_links)), 9)

    def test_existing_local_layers_are_distinguished_from_real_binding(self):
        audit = audit_m62_m66_operational_readiness()

        for field in (
            "m62_exact_scope_present",
            "m63_literals_present",
            "m64_budgets_reconciled",
            "m65_dormant_coordinator_present",
            "m66_exact_parser_present",
            "protected_preflight_components_present",
            "nia_and_bitrix_dispatch_components_present",
            "rollback_contract_and_injected_adapter_present",
        ):
            self.assertTrue(getattr(audit, field), field)
        self.assertFalse(audit.first_confirmation_request_ready)
        self.assertFalse(audit.point_8_can_begin)

    def test_audit_has_no_authority_or_external_effect(self):
        audit = audit_m62_m66_operational_readiness()

        for field in (
            "source_bound",
            "command_available",
            "cli_available",
            "human_attention_required_now",
            "message_request_authorized",
            "real_execution_authorized",
            "persisted",
            "nia_next_called",
            "bitrix_written",
        ):
            self.assertFalse(getattr(audit, field), field)
        self.assertEqual(audit.external_calls, 0)
        self.assertTrue(audit.connector_locked_off)

    def test_gap_set_cannot_be_edited_or_reduced(self):
        audit = audit_m62_m66_operational_readiness()

        with self.assertRaises(ValueError):
            replace(
                audit,
                missing_operational_links=M67_MISSING_OPERATIONAL_LINKS[:-1],
            )

    def test_source_has_no_io_client_command_or_secret_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m67_operational_audit.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "get_dialog(", "get_session_history(", "send_approved_",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
