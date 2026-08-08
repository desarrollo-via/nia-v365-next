import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_source_diagnostic import (
    M86AS_PUBLIC_CATEGORIES,
    M86AS_SOURCE_FAILURE_CATEGORIES,
    build_m86as_source_diagnostic,
)


class M86ASStageSpecificSourceDiagnosticTests(unittest.TestCase):
    def test_three_source_categories_are_exact_and_aggregate(self):
        self.assertEqual(
            M86AS_SOURCE_FAILURE_CATEGORIES,
            (
                "source_factory_unavailable",
                "source_open_unavailable",
                "source_transfer_unavailable",
            ),
        )

    def test_every_source_category_is_public_without_disclosure(self):
        for category in M86AS_SOURCE_FAILURE_CATEGORIES:
            result = build_m86as_source_diagnostic(category)
            self.assertEqual((result.state, result.failure_category), ("NO-GO", category))
            self.assertFalse(result.individual_key_disclosed)
            self.assertFalse(result.value_disclosed)
            self.assertFalse(result.length_disclosed)
            self.assertFalse(result.progress_count_disclosed)

    def test_unknown_category_fails_closed(self):
        self.assertNotIn("source_aggregate_unavailable", M86AS_PUBLIC_CATEGORIES)
        result = build_m86as_source_diagnostic("unexpected")
        self.assertEqual(result.failure_category, "authorization_invalid")


if __name__ == "__main__":
    unittest.main()
