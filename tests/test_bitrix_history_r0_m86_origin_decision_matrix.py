import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_origin_decision_matrix import (
    inspect_m86ab_origin_decision_matrix,
)


ROOT = Path(__file__).resolve().parents[1]


class M86ABOriginDecisionMatrixTests(unittest.TestCase):
    def test_recommends_only_allowlisted_process_environment_design(self):
        matrix = inspect_m86ab_origin_decision_matrix()
        self.assertEqual(matrix.state, "RECOMMENDED-DESIGN-NO-GO")
        self.assertEqual(matrix.recommended_source, "allowlisted-process-environment")
        self.assertEqual(
            matrix.rationale,
            "no_file_no_network_no_circular_target_exact_keys_only",
        )
        self.assertEqual(sum(item.decision == "RECOMMENDED-DESIGN" for item in matrix.options), 1)

    def test_recommended_option_has_no_file_network_or_circular_target(self):
        recommended = inspect_m86ab_origin_decision_matrix().options[0]
        self.assertFalse(recommended.reads_persistent_file)
        self.assertFalse(recommended.requires_network)
        self.assertFalse(recommended.circular_with_missing_target)
        self.assertTrue(recommended.exact_key_access_without_enumeration_possible)
        self.assertEqual(recommended.rank, 1)

    def test_other_options_are_ranked_and_rejected(self):
        options = inspect_m86ab_origin_decision_matrix().options
        self.assertEqual(tuple(item.rank for item in options), (1, 2, 3, 4))
        self.assertEqual(
            tuple(item.source_kind for item in options[1:]),
            ("local-dotenv", "app-settings", "windows-credential-target"),
        )
        self.assertTrue(all(item.decision == "REJECTED" for item in options[1:]))

    def test_recommendation_remains_no_go_without_binding_presence_and_fit(self):
        matrix = inspect_m86ab_origin_decision_matrix()
        self.assertFalse(matrix.real_binding_present)
        self.assertFalse(matrix.aggregate_presence_known)
        self.assertFalse(matrix.aggregate_fit_known)
        self.assertEqual(matrix.current_real_read_budget, 0)
        self.assertFalse(matrix.environment_enumeration_allowed)
        self.assertFalse(matrix.fallback_allowed)

    def test_future_handoff_requirements_are_explicit_but_not_authorized(self):
        matrix = inspect_m86ab_origin_decision_matrix()
        self.assertTrue(matrix.external_injection_owner_required)
        self.assertTrue(matrix.exact_seven_key_reads_required)
        self.assertTrue(matrix.owned_bytearray_handoff_required)
        self.assertFalse(matrix.authorization_text_present)
        self.assertFalse(matrix.values_read)
        self.assertEqual(matrix.external_calls, 0)

    def test_snapshot_preserves_all_barriers(self):
        matrix = inspect_m86ab_origin_decision_matrix()
        self.assertTrue(matrix.connector_locked_off)
        self.assertFalse(matrix.persisted)
        self.assertFalse(matrix.nia_next_called)
        self.assertFalse(matrix.bitrix_written)

    def test_module_has_no_reader_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_origin_decision_matrix.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "path(",
            "open(",
            "os.environ",
            "getenv",
            "ctypes",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
