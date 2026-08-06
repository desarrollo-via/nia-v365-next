import unittest

from bitrix_connector.bitrix_history_r0_m86_public_aggregate_diagnostic import (
    PUBLIC_FAILURE_CATEGORIES,
    build_m86al_public_diagnostic,
)


class M86ALPublicAggregateDiagnosticTests(unittest.TestCase):
    def test_fit_has_no_failure_category(self):
        result = build_m86al_public_diagnostic("none")
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))

    def test_each_public_failure_is_no_go(self):
        for category in PUBLIC_FAILURE_CATEGORIES:
            result = build_m86al_public_diagnostic(category)
            self.assertEqual((result.state, result.failure_category), ("NO-GO", category))

    def test_unknown_category_collapses_to_composition_failed(self):
        result = build_m86al_public_diagnostic("unexpected")
        self.assertEqual(result.failure_category, "composition_failed")

    def test_snapshot_never_discloses_individual_evidence(self):
        result = build_m86al_public_diagnostic("source_aggregate_unavailable")
        self.assertFalse(result.individual_key_disclosed)
        self.assertFalse(result.value_disclosed)
        self.assertFalse(result.length_disclosed)
        self.assertFalse(result.progress_count_disclosed)
        self.assertFalse(result.source_read_calls_disclosed)

    def test_production_barriers_are_intact(self):
        result = build_m86al_public_diagnostic("candidate_not_fit")
        self.assertEqual(result.external_calls, 0)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)


if __name__ == "__main__":
    unittest.main()
