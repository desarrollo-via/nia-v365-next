import unittest

from bitrix_connector.bitrix_history_r0_protected_reader_failure import (
    PROTECTED_READER_FAILURE_CATEGORIES,
    classify_protected_reader_failure,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)


def no_go(reason, *, history_read_calls=0):
    return BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.NO_GO,
        reason=reason,
        dialog_read_calls=1,
        history_read_calls=history_read_calls,
        resources_closed=True,
    )


class ProtectedReaderFailureTests(unittest.TestCase):
    def test_fixed_safe_reasons_have_specific_categories(self):
        expected = {
            "bitrix_history_wait_timeout": "reader_wait_timeout",
            "bitrix_history_barrier_degraded": "reader_barrier_degraded",
            "bitrix_history_dialog_drift": "reader_dialog_drift",
            "bitrix_history_candidate_count_invalid": (
                "reader_candidate_count_invalid"
            ),
            "bitrix_history_controlled_message_mismatch": (
                "reader_controlled_message_mismatch"
            ),
            "bitrix_history_resources_close_failed": (
                "reader_resources_close_failed"
            ),
            "bitrix_history_invalid_envelope": (
                "reader_history_envelope_invalid"
            ),
            "bitrix_history_invalid_collections": (
                "reader_history_collections_invalid"
            ),
            "bitrix_history_invalid_fields": (
                "reader_history_fields_invalid"
            ),
        }
        for reason, category in expected.items():
            with self.subTest(reason=reason):
                self.assertEqual(
                    classify_protected_reader_failure(no_go(reason)),
                    category,
                )

    def test_read_failures_distinguish_dialog_from_history_phase(self):
        for reason, dialog_category, history_category in (
            (
                "bitrix_history_read_unavailable",
                "reader_dialog_unavailable",
                "reader_history_unavailable",
            ),
            (
                "bitrix_history_read_rejected",
                "reader_dialog_rejected",
                "reader_history_rejected",
            ),
            (
                "bitrix_history_invalid_response",
                "reader_dialog_invalid",
                "reader_history_invalid",
            ),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    classify_protected_reader_failure(no_go(reason)),
                    dialog_category,
                )
                self.assertEqual(
                    classify_protected_reader_failure(
                        no_go(reason, history_read_calls=1)
                    ),
                    history_category,
                )

    def test_unknown_or_invalid_result_uses_safe_fallback(self):
        self.assertEqual(
            classify_protected_reader_failure(
                no_go("fictional-private-reader-detail")
            ),
            "reader_other_safe_failure",
        )
        self.assertEqual(
            classify_protected_reader_failure(object()),
            "reader_other_safe_failure",
        )

    def test_every_result_is_in_closed_allowlist(self):
        categories = {
            classify_protected_reader_failure(no_go("bitrix_history_wait_timeout")),
            classify_protected_reader_failure(no_go("unknown")),
            classify_protected_reader_failure(object()),
        }
        self.assertTrue(categories <= PROTECTED_READER_FAILURE_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
