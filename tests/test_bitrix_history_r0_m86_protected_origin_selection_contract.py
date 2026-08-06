import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_protected_origin_selection_contract import (
    M86ZAggregateHandoffContract,
    M86ZOriginCandidate,
    inspect_m86z_protected_origin_selection,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


class M86ZProtectedOriginSelectionContractTests(unittest.TestCase):
    def test_no_source_is_selected_or_defaulted(self):
        contract = inspect_m86z_protected_origin_selection()
        self.assertEqual((contract.phase, contract.state), ("M86-Z", "NO-GO"))
        self.assertEqual(contract.reason, "no_eligible_protected_origin")
        self.assertIsNone(contract.selected_source)
        self.assertFalse(contract.default_source_allowed)
        self.assertFalse(contract.fallback_allowed)
        self.assertEqual(contract.source_reads, 0)
        self.assertFalse(contract.values_loaded)

    def test_all_four_observed_candidates_are_explicitly_rejected(self):
        candidates = inspect_m86z_protected_origin_selection().candidates
        self.assertEqual(
            tuple(item.source_kind for item in candidates),
            (
                "local-dotenv",
                "process-environment",
                "windows-credential-target",
                "app-settings",
            ),
        )
        self.assertTrue(all(item.decision == "REJECTED" for item in candidates))
        self.assertTrue(all(item.current_read_budget == 0 for item in candidates))
        self.assertEqual(
            tuple(item.rejection_reason for item in candidates),
            (
                "current_scope_forbids_dotenv_access",
                "m80_budget_zero_and_no_owned_buffer_handoff",
                "destination_cannot_be_its_own_missing_source",
                "current_scope_forbids_query_and_adapter_absent",
            ),
        )

    def test_handoff_is_one_source_one_transfer_one_probe(self):
        handoff = inspect_m86z_protected_origin_selection().handoff
        self.assertEqual(handoff.required_names, PROTECTED_SETTING_NAMES)
        self.assertTrue(handoff.exact_order_required)
        self.assertTrue(handoff.owned_bytearray_values_required)
        self.assertEqual((handoff.ownership_transfer_budget, handoff.fit_probe_budget), (1, 1))
        self.assertTrue(handoff.source_close_before_public_result)
        self.assertTrue(handoff.probe_consumes_and_zeroizes_all_buffers)
        self.assertFalse(handoff.fallback_allowed)
        self.assertFalse(handoff.multiple_sources_allowed)

    def test_public_handoff_never_exposes_presence_or_lengths(self):
        handoff = inspect_m86z_protected_origin_selection().handoff
        self.assertFalse(handoff.individual_presence_public)
        self.assertFalse(handoff.individual_lengths_public)
        self.assertFalse(handoff.aggregate_length_public)
        self.assertEqual(handoff.public_result, ("FIT", "NO-GO"))

    def test_invalid_candidate_and_handoff_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "origin_candidate_invalid"):
            M86ZOriginCandidate(
                source_kind="local-dotenv",
                local_implementation_state="",
                rejection_reason="reason",
            )
        with self.assertRaisesRegex(ValueError, "handoff_contract_invalid"):
            M86ZAggregateHandoffContract(required_names=PROTECTED_SETTING_NAMES[:-1])

    def test_snapshot_has_no_authorization_runtime_or_effects(self):
        contract = inspect_m86z_protected_origin_selection()
        self.assertFalse(contract.real_authorization_literals_present)
        self.assertEqual((contract.operating_system_calls, contract.external_calls), (0, 0))
        self.assertTrue(contract.connector_locked_off)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_next_called)
        self.assertFalse(contract.bitrix_written)

    def test_module_has_no_source_reader_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_protected_origin_selection_contract.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "path(",
            "open(",
            "ctypes",
            "windll",
            "credreadw",
            "credwritew",
            "os.environ",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
