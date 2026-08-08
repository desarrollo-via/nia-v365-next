import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_FORMAT,
    MAX_M84_BLOB_BYTES,
    WINDOWS_CREDENTIAL_BLOB_MAX_BYTES,
)
from bitrix_connector.bitrix_history_r0_m86_sealed_provisioning_port_contract import (
    M86WBranchBudget,
    M86W_FAILURE_CATEGORIES,
    inspect_m86w_sealed_provisioning_port_contract,
)


ROOT = Path(__file__).resolve().parents[1]


class M86WSealedProvisioningPortContractTests(unittest.TestCase):
    def test_contract_is_designed_no_go_without_runtime_port(self):
        contract = inspect_m86w_sealed_provisioning_port_contract()
        self.assertEqual((contract.phase, contract.state), ("M86-W", "DESIGNED-INERT"))
        self.assertEqual(contract.reason, "runtime_port_not_implemented")
        self.assertEqual(contract.target_id, M80_CREDENTIAL_TARGET_ID)
        self.assertEqual(contract.blob_format, M84_BLOB_FORMAT)
        self.assertFalse(contract.implementation_present)
        self.assertFalse(contract.native_factory_present)
        self.assertFalse(contract.real_value_source_bound)
        self.assertFalse(contract.real_authorization_literals_present)
        self.assertFalse(contract.real_execution_authorized)

    def test_local_native_and_effective_limits_are_reconciled_to_2560(self):
        contract = inspect_m86w_sealed_provisioning_port_contract()
        self.assertEqual(MAX_M84_BLOB_BYTES, 2560)
        self.assertEqual(WINDOWS_CREDENTIAL_BLOB_MAX_BYTES, 2560)
        self.assertEqual(contract.local_parser_max_blob_bytes, 2560)
        self.assertEqual(contract.native_max_blob_bytes, 2560)
        self.assertTrue(contract.native_blob_limit_verified)
        self.assertEqual(contract.effective_max_blob_bytes, 2560)
        self.assertEqual(
            contract.native_limit_source,
            "https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw",
        )

    def test_prior_state_proof_never_conflates_absence_with_access_failure(self):
        proof = inspect_m86w_sealed_provisioning_port_contract().prior_proof
        self.assertEqual(proof.target_id, M80_CREDENTIAL_TARGET_ID)
        self.assertEqual(proof.accepted_states, ("absent", "present"))
        self.assertTrue(proof.ambiguous_is_no_go)
        self.assertTrue(proof.absence_requires_exact_native_not_found_classification)
        self.assertTrue(proof.access_or_api_failure_is_not_absence)
        self.assertTrue(proof.present_requires_successful_exact_target_read)
        self.assertTrue(proof.present_backup_in_owned_bytearray)
        self.assertTrue(proof.present_backup_never_parsed_for_public_output)
        self.assertFalse(proof.public_blob_length_allowed)
        self.assertFalse(proof.public_blob_digest_allowed)
        self.assertFalse(proof.public_native_error_allowed)
        self.assertEqual(proof.enumeration_budget, 0)
        self.assertTrue(proof.backup_zeroized_in_finally)

    def test_branch_budgets_are_exact_one_shot_and_reversible(self):
        absent, present = inspect_m86w_sealed_provisioning_port_contract().branch_budgets
        self.assertEqual(
            (
                absent.prior_state,
                absent.exact_target_read_budget,
                absent.candidate_apply_budget,
                absent.restore_write_budget,
                absent.delete_budget,
            ),
            ("absent", 3, 1, 0, 1),
        )
        self.assertEqual(
            (
                present.prior_state,
                present.exact_target_read_budget,
                present.candidate_apply_budget,
                present.restore_write_budget,
                present.delete_budget,
            ),
            ("present", 3, 1, 1, 0),
        )
        for branch in (absent, present):
            self.assertEqual((branch.enumeration_budget, branch.retry_budget), (0, 0))

    def test_invalid_branch_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "branch_budget_invalid"):
            M86WBranchBudget(
                prior_state="absent",
                exact_target_read_budget=2,
                delete_budget=1,
            )

    def test_failure_categories_are_closed_unique_and_cover_rollback(self):
        contract = inspect_m86w_sealed_provisioning_port_contract()
        self.assertEqual(contract.failure_categories, M86W_FAILURE_CATEGORIES)
        self.assertEqual(len(contract.failure_categories), len(set(contract.failure_categories)))
        self.assertEqual(contract.failure_categories[0], "none")
        for category in (
            "prior_state_ambiguous",
            "candidate_blob_invalid",
            "apply_verification_failed",
            "rollback_delete_failed",
            "rollback_restore_failed",
            "rollback_verification_failed",
            "resource_close_failed",
        ):
            self.assertIn(category, contract.failure_categories)
        self.assertTrue(contract.public_failure_category_only)
        self.assertFalse(contract.private_native_detail_retained)

    def test_sequence_ends_with_zeroization_and_close_and_snapshot_is_inert(self):
        contract = inspect_m86w_sealed_provisioning_port_contract()
        self.assertEqual(
            contract.operation_sequence[-1],
            "zeroize_all_owned_blobs_and_close_in_finally",
        )
        self.assertTrue(contract.owned_candidate_zeroized_in_finally)
        self.assertTrue(contract.owned_prior_backup_zeroized_in_finally)
        self.assertTrue(contract.close_exactly_once)
        self.assertEqual((contract.external_calls, contract.operating_system_calls), (0, 0))
        self.assertTrue(contract.connector_locked_off)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_next_called)
        self.assertFalse(contract.bitrix_written)

    def test_module_contains_no_native_api_source_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_sealed_provisioning_port_contract.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "protocol",
            "ctypes",
            "windll",
            "credwritew",
            "creddeletew",
            "credenumeratew",
            "credreadw",
            "dotenv",
            "os.environ",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
