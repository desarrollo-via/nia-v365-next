import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
    M80_M63_SOURCE_CLAUSE_REPLACEMENT,
    M80_REAL_OWNER_BINDINGS,
    design_m80_windows_credential_owner,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


class M80WindowsCredentialContractTests(unittest.TestCase):
    def test_credential_manager_can_cover_exact_allowlist_by_contract(self):
        contract = design_m80_windows_credential_owner().source_contract
        self.assertEqual(contract.allowed_names, PROTECTED_SETTING_NAMES)
        self.assertEqual(contract.target_id, M80_CREDENTIAL_TARGET_ID)
        self.assertTrue(contract.satisfies_m63_allowlist_by_contract)
        self.assertFalse(contract.changes_external_budgets)

    def test_source_is_one_record_without_enumeration_writes_or_fallback(self):
        contract = design_m80_windows_credential_owner().source_contract
        self.assertEqual(contract.credential_record_read_budget, 1)
        self.assertEqual(contract.helper_buffer_read_budget, 7)
        self.assertEqual(contract.credential_enumeration_budget, 0)
        self.assertEqual(contract.credential_write_budget, 0)
        self.assertEqual(contract.credential_delete_budget, 0)
        self.assertEqual(contract.process_environment_read_budget, 0)
        self.assertEqual(contract.dotenv_read_budget, 0)
        self.assertFalse(contract.fallback_allowed)

    def test_source_contract_is_redacted_closed_and_not_implemented(self):
        contract = design_m80_windows_credential_owner().source_contract
        self.assertFalse(contract.values_leave_owner_memory)
        self.assertFalse(contract.public_individual_presence_flags)
        self.assertTrue(contract.aggregate_ready_or_no_go_only)
        self.assertTrue(contract.close_and_zeroize_in_finally)
        self.assertFalse(contract.implementation_present)
        self.assertFalse(contract.dependency_declared)
        self.assertFalse(contract.credential_record_verified)
        self.assertFalse(contract.source_opened)

    def test_exact_six_real_owner_bindings_are_designed_once(self):
        audit = design_m80_windows_credential_owner()
        self.assertEqual(audit.owner_bindings, M80_REAL_OWNER_BINDINGS)
        self.assertEqual(len(audit.owner_bindings), 6)
        self.assertEqual(len({item.boundary for item in audit.owner_bindings}), 6)
        self.assertTrue(all(not item.implementation_present for item in audit.owner_bindings))
        self.assertTrue(all(item.retry_budget == 0 for item in audit.owner_bindings))

    def test_owner_sequence_preserves_two_confirmations_and_human_boundary(self):
        sequence = design_m80_windows_credential_owner().owner_sequence.sequence
        self.assertLess(sequence.index("consume_first_exact_confirmation"), sequence.index("run_fresh_combined_preflight_once"))
        self.assertLess(sequence.index("consume_second_exact_confirmation"), sequence.index("emit_waiting_message_attention_and_accept_one_signal"))
        self.assertLess(sequence.index("emit_waiting_message_attention_and_accept_one_signal"), sequence.index("run_exact_same_chat_roundtrip_once"))
        self.assertEqual(sequence[-1], "close_every_private_resource_in_finally")

    def test_owner_budgets_remain_closed(self):
        owner = design_m80_windows_credential_owner().owner_sequence
        self.assertEqual(owner.maximum_window_seconds, 180)
        self.assertEqual(owner.retry_budget, 0)
        self.assertEqual(owner.oauth_refresh_budget, 0)
        self.assertEqual(owner.other_chat_budget, 0)
        self.assertEqual(owner.persistence_budget, 0)
        self.assertEqual(owner.production_configuration_mutation_budget, 0)

    def test_m63_delta_is_literal_but_not_applied(self):
        audit = design_m80_windows_credential_owner()
        self.assertIn(M80_CREDENTIAL_TARGET_ID, M80_M63_SOURCE_CLAUSE_REPLACEMENT)
        self.assertIn("Administrador de credenciales de Windows", M80_M63_SOURCE_CLAUSE_REPLACEMENT)
        self.assertIn("sin enumerar otras credenciales", M80_M63_SOURCE_CLAUSE_REPLACEMENT)
        self.assertIn("sin fallback a dotenv", M80_M63_SOURCE_CLAUSE_REPLACEMENT)
        self.assertTrue(audit.m63_source_clause_delta_ready)
        self.assertFalse(audit.m63_modified)

    def test_design_remains_no_go_without_attention_or_execution(self):
        audit = design_m80_windows_credential_owner()
        self.assertEqual((audit.state, audit.credential_decision), ("DESIGNED-NO-GO", "CAPABLE-BY-CONTRACT"))
        self.assertEqual(audit.first_confirmation_decision, "DO-NOT-REQUEST")
        for field in (
            "first_confirmation_request_ready", "attention_required_now",
            "human_message_required_now", "source_bound", "command_available",
            "real_execution_authorized", "persisted", "nia_next_called",
            "bitrix_written",
        ):
            self.assertFalse(getattr(audit, field), field)
        self.assertEqual(audit.external_calls, 0)
        self.assertTrue(audit.connector_locked_off)

    def test_invalid_binding_ledger_is_rejected(self):
        audit = design_m80_windows_credential_owner()
        with self.assertRaises(ValueError):
            replace(audit, owner_bindings=audit.owner_bindings[:-1])

    def test_source_has_no_credential_io_clients_commands_or_attention_effect(self):
        source = (ROOT / "bitrix_connector" / "bitrix_history_r0_m80_windows_credential_contract.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "win32cred", "keyring", "ctypes", "credread", "credenumerate",
            "httpx", "pymongo", "argparse", "input(", "subprocess", "socket",
            "open(", "async def", "os.environ", "print(", "toast", "messagebox",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
