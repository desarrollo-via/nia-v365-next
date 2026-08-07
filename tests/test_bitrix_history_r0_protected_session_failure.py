import unittest

from bitrix_connector.bitrix_history_r0_protected_session_failure import (
    normalize_protected_session_failure_category,
)


class ProtectedSessionFailureCategoryTests(unittest.TestCase):
    def test_known_category_is_preserved(self):
        self.assertEqual(
            normalize_protected_session_failure_category(
                "dialog_identity_mismatch",
                fallback="other_safe_failure",
            ),
            "dialog_identity_mismatch",
        )

    def test_reader_category_is_preserved(self):
        self.assertEqual(
            normalize_protected_session_failure_category(
                "reader_wait_timeout",
                fallback="other_safe_failure",
            ),
            "reader_wait_timeout",
        )

    def test_unknown_category_is_reduced_to_allowlisted_fallback(self):
        self.assertEqual(
            normalize_protected_session_failure_category(
                "fictional-private-category",
                fallback="other_safe_failure",
            ),
            "other_safe_failure",
        )


if __name__ == "__main__":
    unittest.main()
