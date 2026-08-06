import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_adapter import (
    HistoryR0SelectionStatus,
    select_controlled_history_message,
)
from bitrix_connector.bitrix_history_r0_candidate_aware_normalizer import (
    CandidateAwareNormalizationStatus,
    normalize_candidate_aware_history_payload,
)


ROOT = Path(__file__).resolve().parents[1]
HUMAN_TEXT = "mensaje humano fixture m54"
HUMAN_HASH = hashlib.sha256(HUMAN_TEXT.encode("utf-8")).hexdigest()
WINDOW_START = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)


def human_message(**updates):
    payload = {
        "id": 701,
        "chatid": 78733,
        "senderid": 51,
        "recipientid": "chat78733",
        "date": "2026-08-03T15:00:01+00:00",
        "text": HUMAN_TEXT,
    }
    payload.update(updates)
    return payload


def raw_payload(*, messages=None, users=None):
    return {
        "result": {
            "chatId": 78733,
            "sessionId": 900,
            "message": messages if messages is not None else [human_message()],
            "users": users
            if users is not None
            else [
                {"id": 51, "connector": True},
                {"id": 245339, "connector": False},
            ],
        }
    }


def normalize(payload):
    return normalize_candidate_aware_history_payload(
        payload=payload,
        expected_chat_id=78733,
        expected_dialog_id="chat78733",
        expected_session_id=900,
        baseline_message_id=700,
        expected_sender_id=51,
    )


def select(history):
    return select_controlled_history_message(
        history=history,
        expected_chat_id=78733,
        expected_dialog_id="chat78733",
        expected_session_id=900,
        baseline_message_id=700,
        expected_text_sha256=HUMAN_HASH,
        window_start=WINDOW_START,
        window_end=WINDOW_START + timedelta(seconds=180),
        expected_sender_id=51,
    )


class CandidateAwareHistoryNormalizerTests(unittest.TestCase):
    def test_normalizes_human_and_ignores_incomplete_bot_reply(self):
        payload = raw_payload(
            messages=[
                human_message(),
                {"senderId": 245339, "text": None, "date": None},
            ]
        )

        result = normalize(payload)
        selected = select(result.history)

        self.assertEqual(result.status, CandidateAwareNormalizationStatus.NORMALIZED)
        self.assertEqual(result.input_message_count, 2)
        self.assertEqual(result.normalized_message_count, 1)
        self.assertEqual(result.ignored_non_candidate_count, 1)
        self.assertEqual(selected.status, HistoryR0SelectionStatus.SELECTED)
        self.assertEqual(selected.candidate_count, 1)

    def test_accepts_dense_indexed_collections_and_explicit_camel_aliases(self):
        camel_human = {
            "ID": "701",
            "chatId": "78733",
            "senderId": "51",
            "recipientId": "chat78733",
            "DATE": "2026-08-03T15:00:01+00:00",
            "TEXT": HUMAN_TEXT,
            "PARAMS": {},
        }
        payload = {
            "RESULT": {
                "CHAT_ID": "78733",
                "SESSION_ID": "900",
                "messages": {"0": camel_human, "1": {"sender_id": "245339"}},
                "USERS": {
                    "0": {"ID": "51", "isConnector": "Y"},
                    "1": {"ID": "245339", "CONNECTOR": "N"},
                },
            }
        }

        result = normalize(payload)

        self.assertEqual(result.status, CandidateAwareNormalizationStatus.NORMALIZED)
        self.assertEqual(select(result.history).status, HistoryR0SelectionStatus.SELECTED)

    def test_classifies_invalid_envelope(self):
        for payload in (None, [], {"result": []}, {"RESULT": {}, "result": {}}):
            with self.subTest(payload_type=type(payload).__name__):
                result = normalize(payload)
                self.assertEqual(result.status, CandidateAwareNormalizationStatus.NO_GO)
                self.assertEqual(
                    result.failure_category,
                    "reader_history_envelope_invalid",
                )

    def test_classifies_invalid_collections(self):
        cases = []
        wrong_type = raw_payload()
        wrong_type["result"]["message"] = "not-a-collection"
        cases.append(wrong_type)
        sparse = raw_payload()
        sparse["result"]["message"] = {"1": human_message()}
        cases.append(sparse)
        named = raw_payload()
        named["result"]["users"] = {"human": {"id": 51, "connector": True}}
        cases.append(named)

        for payload in cases:
            with self.subTest(payload=payload):
                result = normalize(payload)
                self.assertEqual(
                    result.failure_category,
                    "reader_history_collections_invalid",
                )

    def test_rejects_missing_or_ambiguous_required_fields(self):
        cases = []
        missing_session = raw_payload()
        del missing_session["result"]["sessionId"]
        cases.append(missing_session)
        missing_human_text = raw_payload(messages=[human_message()])
        del missing_human_text["result"]["message"][0]["text"]
        cases.append(missing_human_text)
        unknown_sender = raw_payload(messages=[{"senderid": 999}])
        cases.append(unknown_sender)
        duplicate_alias = raw_payload(messages=[human_message(senderId=51)])
        cases.append(duplicate_alias)
        non_explicit_boolean = raw_payload(
            users=[{"id": 51, "connector": 1.0}]
        )
        cases.append(non_explicit_boolean)

        for payload in cases:
            with self.subTest(payload=payload):
                result = normalize(payload)
                self.assertEqual(
                    result.failure_category,
                    "reader_history_fields_invalid",
                )

    def test_rejects_duplicate_users_and_identity_mismatch(self):
        duplicates = raw_payload(
            users=[
                {"id": 51, "connector": True},
                {"ID": 51, "CONNECTOR": True},
            ]
        )
        mismatch = raw_payload()
        mismatch["result"]["chatId"] = 999

        for payload in (duplicates, mismatch):
            with self.subTest(payload=payload):
                self.assertEqual(
                    normalize(payload).failure_category,
                    "reader_history_fields_invalid",
                )

    def test_public_output_excludes_payload_and_private_history(self):
        result = normalize(
            raw_payload(
                messages=[
                    human_message(),
                    {"senderid": 245339, "text": "respuesta bot fixture"},
                ]
            )
        )
        rendered = result.model_dump_json()

        for forbidden in (
            HUMAN_TEXT,
            HUMAN_HASH,
            "78733",
            "900",
            "701",
            "245339",
            "respuesta bot fixture",
            "senderid",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertNotIn(HUMAN_TEXT, repr(result))
        self.assertTrue(result.fixture_only)
        self.assertFalse(result.real_form_identified)
        self.assertEqual(result.external_calls, 0)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_invalid_contract_raises_before_normalization(self):
        with self.assertRaises(ValueError):
            normalize_candidate_aware_history_payload(
                payload=raw_payload(),
                expected_chat_id=78733,
                expected_dialog_id="chat999",
                expected_session_id=900,
                baseline_message_id=700,
            )

    def test_source_has_no_client_io_wait_or_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_candidate_aware_normalizer.py"
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
