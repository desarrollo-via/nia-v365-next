import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_client import BitrixSessionHistory
from bitrix_connector.bitrix_history_r0_validated_selector import (
    ValidatedHistorySelectionStatus,
    select_exact_controlled_human_message,
)


ROOT = Path(__file__).resolve().parents[1]
HUMAN_TEXT = "mensaje humano controlado fixture"
HUMAN_HASH = hashlib.sha256(HUMAN_TEXT.encode("utf-8")).hexdigest()
WINDOW_START = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)


def message(
    message_id,
    sender_id,
    text,
    *,
    date="2026-08-03T15:00:01+00:00",
    chat_id=78733,
    recipient_id="chat78733",
    params=None,
):
    return {
        "id": message_id,
        "chatid": chat_id,
        "senderid": sender_id,
        "recipientid": recipient_id,
        "date": date,
        "text": text,
        "params": params or {},
    }


def history(*, messages=None, chat_id=78733, session_id=900):
    return BitrixSessionHistory.model_validate(
        {
            "chatId": chat_id,
            "sessionId": session_id,
            "message": messages
            if messages is not None
            else [message(701, 51, HUMAN_TEXT)],
            "users": [
                {"id": 51, "connector": True},
                {"id": 245339, "connector": False},
                {"id": 99, "connector": False},
            ],
        }
    )


def select(current_history):
    return select_exact_controlled_human_message(
        history=current_history,
        expected_chat_id=78733,
        expected_dialog_id="chat78733",
        expected_session_id=900,
        expected_sender_id=51,
        baseline_message_id=700,
        expected_text_sha256=HUMAN_HASH,
        window_start=WINDOW_START,
        window_end=WINDOW_START + timedelta(seconds=180),
    )


class ValidatedHistorySelectorTests(unittest.TestCase):
    def test_selects_human_with_subsequent_bot_reply_and_unrelated_entries(self):
        fixture = history(
            messages=[
                message(699, 51, "entrada anterior"),
                message(701, 51, HUMAN_TEXT),
                message(702, 245339, "respuesta posterior del bot fixture"),
                message(703, 99, "entrada de operador no candidata"),
                message(704, 99, "evento", params={"IS_SYSTEM": "Y"}),
            ]
        )

        result = select(fixture)

        self.assertEqual(result.status, ValidatedHistorySelectionStatus.SELECTED)
        self.assertEqual(result.candidate_count, 1)
        self.assertTrue(result.controlled_human_message_verified)
        self.assertEqual(result.phase, "M52")

    def test_bot_reply_is_never_candidate_even_if_text_matches(self):
        result = select(history(messages=[message(701, 245339, HUMAN_TEXT)]))

        self.assertEqual(result.status, ValidatedHistorySelectionStatus.NO_GO)
        self.assertEqual(result.candidate_count, 0)

    def test_rejects_zero_exact_human_candidates(self):
        variants = (
            message(701, 51, "texto distinto"),
            message(701, 51, HUMAN_TEXT, date="2026-08-03T14:59:59+00:00"),
            message(701, 99, HUMAN_TEXT),
            message(700, 51, HUMAN_TEXT),
            message(701, 51, HUMAN_TEXT, recipient_id="chat999"),
            message(701, 51, HUMAN_TEXT, params={"SYSTEM": True}),
        )
        for current in variants:
            with self.subTest(current_id=current["id"], sender=current["senderid"]):
                result = select(history(messages=[current]))
                self.assertEqual(result.status, ValidatedHistorySelectionStatus.NO_GO)
                self.assertEqual(result.candidate_count, 0)
                self.assertFalse(result.controlled_human_message_verified)

    def test_rejects_multiple_exact_human_candidates(self):
        result = select(
            history(
                messages=[
                    message(701, 51, HUMAN_TEXT),
                    message(702, 51, HUMAN_TEXT),
                    message(703, 245339, "respuesta del bot fixture"),
                ]
            )
        )

        self.assertEqual(result.status, ValidatedHistorySelectionStatus.NO_GO)
        self.assertEqual(result.candidate_count, 2)

    def test_rejects_history_identity_before_counting_candidates(self):
        for fixture in (history(chat_id=78734), history(session_id=901)):
            with self.subTest(chat=fixture.chat_id, session=fixture.session_id):
                result = select(fixture)
                self.assertEqual(
                    result.reason,
                    "bitrix_validated_history_identity_mismatch",
                )
                self.assertEqual(result.candidate_count, 0)

    def test_public_result_excludes_all_private_inputs_and_message_data(self):
        result = select(history())
        dumped = result.model_dump_json()

        for forbidden in (
            HUMAN_TEXT,
            HUMAN_HASH,
            "78733",
            "900",
            "701",
            "51",
            "2026-08-03",
            "sender",
            "message_id",
        ):
            self.assertNotIn(forbidden, dumped)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_invalid_private_contract_fails_closed(self):
        kwargs = {
            "history": history(),
            "expected_chat_id": 78733,
            "expected_dialog_id": "chat78733",
            "expected_session_id": 900,
            "expected_sender_id": 51,
            "baseline_message_id": 700,
            "expected_text_sha256": HUMAN_HASH,
            "window_start": WINDOW_START,
            "window_end": WINDOW_START + timedelta(seconds=180),
        }
        invalid = (
            {"expected_dialog_id": "chat999"},
            {"expected_sender_id": 0},
            {"expected_text_sha256": "not-a-hash"},
            {"window_end": WINDOW_START},
            {"window_start": WINDOW_START.replace(tzinfo=None)},
        )
        for replacement in invalid:
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError):
                    select_exact_controlled_human_message(**(kwargs | replacement))

    def test_source_has_no_io_wait_message_or_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_validated_selector.py"
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
            "asyncio",
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
