import unittest
from pathlib import Path

from pydantic import ValidationError

from bitrix_connector.bitrix_history_r0_existing_receipt_contract import (
    EXISTING_HISTORY_RECEIPT_CONTRACT,
    ExistingHistoryReceiptContract,
)


ROOT = Path(__file__).resolve().parents[1]


class ExistingHistoryReceiptContractTests(unittest.TestCase):
    def test_reuses_one_history_response_and_validates_shape_first(self):
        contract = EXISTING_HISTORY_RECEIPT_CONTRACT

        self.assertEqual(contract.phase, "M51")
        self.assertEqual(contract.state, "PREPARED")
        self.assertTrue(contract.single_history_response_reused)
        self.assertFalse(contract.second_history_read_allowed)
        self.assertTrue(contract.shape_validation_precedes_selection)
        self.assertTrue(contract.invalid_shape_stops_before_selection)

    def test_existing_bot_reply_is_allowed_but_never_the_candidate(self):
        contract = EXISTING_HISTORY_RECEIPT_CONTRACT

        self.assertTrue(contract.multiple_history_entries_allowed)
        self.assertTrue(contract.unrelated_entries_allowed)
        self.assertTrue(contract.subsequent_existing_bot_reply_allowed)
        self.assertFalse(contract.subsequent_existing_bot_reply_is_candidate)
        self.assertFalse(contract.whole_history_single_candidate_required)
        self.assertEqual(contract.controlled_candidate_count_required, 1)
        self.assertFalse(contract.current_bot_is_nia_next)
        self.assertFalse(contract.existing_bot_activity_changes_nia_next_called)

    def test_candidate_requires_private_text_window_and_identity_checks(self):
        contract = EXISTING_HISTORY_RECEIPT_CONTRACT

        for field in (
            "private_expected_text_or_hash_required",
            "private_time_window_required",
            "controlled_chat_identity_required",
            "controlled_session_identity_required",
            "candidate_timestamp_in_window_required",
            "candidate_text_match_required",
            "candidate_identity_consistent_required",
            "authentic_receipt_requires_unique_controlled_candidate",
        ):
            self.assertTrue(getattr(contract, field), field)
        self.assertFalse(contract.authentic_receipt_proven)
        self.assertFalse(contract.checklist_38_completed)

    def test_no_message_wait_nia_next_or_mutation_is_permitted(self):
        contract = EXISTING_HISTORY_RECEIPT_CONTRACT

        self.assertEqual(contract.nia_next_call_budget, 0)
        self.assertEqual(contract.message_send_budget, 0)
        self.assertEqual(contract.wait_budget, 0)
        self.assertEqual(contract.mutation_budget, 0)
        self.assertFalse(contract.human_message_required)
        self.assertFalse(contract.waiting_message_allowed)
        self.assertTrue(contract.connector_locked_off)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_next_called)
        self.assertFalse(contract.bitrix_written)

    def test_public_output_excludes_both_messages_and_private_inputs(self):
        contract = EXISTING_HISTORY_RECEIPT_CONTRACT

        for field in (
            "output_status_only",
            "output_safe_reason_only",
            "output_candidate_count_only",
            "output_verification_booleans_only",
        ):
            self.assertTrue(getattr(contract, field), field)
        for field in (
            "output_message_content",
            "output_expected_text_or_hash",
            "output_time_window",
            "output_session_identity",
            "output_sender_identity",
            "output_bot_reply_content",
        ):
            self.assertFalse(getattr(contract, field), field)

    def test_contract_is_strict_inert_and_has_no_execution_surface(self):
        contract = EXISTING_HISTORY_RECEIPT_CONTRACT

        self.assertFalse(contract.command_available)
        self.assertFalse(contract.cli_available)
        self.assertFalse(contract.source_bound)
        self.assertFalse(contract.real_execution_authorized)
        for field in (
            "dialog_read_calls",
            "history_read_calls",
            "candidate_count",
            "mutation_calls",
            "external_calls",
        ):
            self.assertEqual(getattr(contract, field), 0, field)
        with self.assertRaises(ValidationError):
            ExistingHistoryReceiptContract(extra_field=True)
        with self.assertRaises(ValidationError):
            ExistingHistoryReceiptContract(candidate_count=1)

        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_existing_receipt_contract.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".open(",
            "dotenv",
            "os.environ",
            "get_dialog(",
            "get_session_history(",
            "sleep(",
            "waiting-message",
            "send_message",
            "input(",
            "asyncio.run",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "execute=true",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
