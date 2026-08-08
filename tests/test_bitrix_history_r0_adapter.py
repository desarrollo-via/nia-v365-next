import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from bitrix_connector.bitrix_history_r0_adapter import (
    BITRIX_HISTORY_R0_ORIGIN,
    HistoryR0SelectionStatus,
    select_controlled_history_message,
)
from bitrix_connector.bitrix_history_r0_client import BitrixSessionHistory


MESSAGE_TEXT = "mensaje controlado único"
MESSAGE_HASH = hashlib.sha256(MESSAGE_TEXT.encode("utf-8")).hexdigest()
WINDOW_START = datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)


def history_payload(*, messages=None, users=None, chat_id=78733, session_id=900):
    return BitrixSessionHistory.model_validate({
        "chatId": chat_id,
        "sessionId": session_id,
        "message": messages if messages is not None else [{
            "id": 701,
            "chatid": 78733,
            "senderid": 51,
            "recipientid": "chat78733",
            "date": "2026-07-31T15:00:01+00:00",
            "text": MESSAGE_TEXT,
        }],
        "users": users if users is not None else [{
            "id": 51,
            "connector": True,
        }],
    })


def select(history):
    return select_controlled_history_message(
        history=history,
        expected_chat_id=78733,
        expected_dialog_id="chat78733",
        expected_session_id=900,
        baseline_message_id=700,
        expected_text_sha256=MESSAGE_HASH,
        window_start=WINDOW_START,
        window_end=WINDOW_START + timedelta(seconds=180),
    )


class BitrixHistoryR0AdapterTests(unittest.TestCase):
    def test_selects_exact_message_without_projecting_text_or_author(self):
        result = select(history_payload())

        self.assertEqual(result.status, HistoryR0SelectionStatus.SELECTED)
        self.assertEqual(result.candidate.origin, BITRIX_HISTORY_R0_ORIGIN)
        self.assertNotIn(MESSAGE_TEXT, repr(result))
        dumped = result.model_dump(mode="json")
        self.assertNotIn("text", dumped["candidate"])
        self.assertNotIn("senderid", str(dumped))

    def test_rejects_identity_hash_author_time_and_multiple_candidates(self):
        base = history_payload().model_dump(by_alias=True)
        cases = []
        wrong_hash_message = dict(base["message"][0], text="otro")
        cases.append(history_payload(messages=[wrong_hash_message]))
        cases.append(history_payload(users=[{"id": 51, "connector": False}]))
        old_message = dict(base["message"][0], date="2026-07-31T14:59:59+00:00")
        cases.append(history_payload(messages=[old_message]))
        cases.append(history_payload(chat_id=78734))
        second = dict(base["message"][0], id=702)
        cases.append(history_payload(messages=[base["message"][0], second]))

        for current in cases:
            with self.subTest(current=current):
                result = select(current)
                self.assertEqual(result.status, HistoryR0SelectionStatus.NO_GO)
                self.assertIsNone(result.candidate)

    def test_ignores_explicit_system_message_but_not_operator_message(self):
        base = history_payload().model_dump(by_alias=True)
        system = dict(
            base["message"][0],
            id=702,
            params={"IS_SYSTEM": "Y"},
        )
        selected = select(history_payload(messages=[base["message"][0], system]))
        self.assertEqual(selected.status, HistoryR0SelectionStatus.SELECTED)

    def test_ignores_subsequent_existing_bot_reply(self):
        base = history_payload().model_dump(by_alias=True)
        bot_reply = dict(
            base["message"][0],
            id=702,
            senderid=245339,
            text="respuesta posterior del bot fixture",
        )
        selected = select(
            history_payload(
                messages=[base["message"][0], bot_reply],
                users=[
                    {"id": 51, "connector": True},
                    {"id": 245339, "connector": False},
                ],
            )
        )

        self.assertEqual(selected.status, HistoryR0SelectionStatus.SELECTED)
        self.assertEqual(selected.candidate_count, 1)


if __name__ == "__main__":
    unittest.main()
