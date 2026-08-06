import unittest
from pathlib import Path

from pydantic import ValidationError

from bitrix_connector.bitrix_history_r0_reply_rollback_contract import (
    BITRIX_REPLY_DELETE_METHOD,
    ReplyRollbackDeletePreview,
    ReplyRollbackStatus,
    build_reply_rollback_delete_preview,
    verify_reply_rollback_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
SENT_ID = 800
DEFAULT = object()


def history(*, messages=None, chat_id=78733, session_id=900):
    return {
        "result": {
            "chatId": chat_id,
            "sessionId": session_id,
            "message": messages
            if messages is not None
            else {
                "701": {"id": "701", "text": "fixture humano"},
                "702": {"id": "702", "text": "fixture bot previo"},
            },
        }
    }


def verify(delete_response=DEFAULT, current_history=DEFAULT):
    return verify_reply_rollback_fixture(
        preview=build_reply_rollback_delete_preview(
            bot_id=373259,
            sent_message_id=SENT_ID,
        ),
        delete_response=delete_response
        if delete_response is not DEFAULT
        else {"result": {"result": True}},
        post_delete_history_response=current_history
        if current_history is not DEFAULT
        else history(),
        expected_chat_id=78733,
        expected_session_id=900,
    )


class ReplyRollbackContractTests(unittest.TestCase):
    def test_preview_uses_official_v2_method_and_complete_deletion(self):
        preview = build_reply_rollback_delete_preview(
            bot_id=373259,
            sent_message_id=SENT_ID,
        )

        self.assertEqual(preview.method, BITRIX_REPLY_DELETE_METHOD)
        self.assertEqual(preview.botId, 373259)
        self.assertEqual(preview.messageId, SENT_ID)
        self.assertTrue(preview.complete)

    def test_fixture_contract_accepts_nested_true_and_exact_absence(self):
        result = verify()

        self.assertEqual(result.status, ReplyRollbackStatus.VERIFIED)
        self.assertEqual(result.reason, "reply_rollback_fixture_verified")
        self.assertTrue(result.fixture_delete_response_accepted)
        self.assertTrue(result.fixture_target_absent_after_delete)
        self.assertTrue(result.rollback_contract_locally_tested)
        self.assertTrue(result.verification_strategy_is_documented_contract_inference)

    def test_target_still_present_is_no_go(self):
        result = verify(
            current_history=history(
                messages={str(SENT_ID): {"id": SENT_ID}}
            )
        )

        self.assertEqual(result.status, ReplyRollbackStatus.NO_GO)
        self.assertEqual(result.reason, "reply_rollback_target_still_present")
        self.assertTrue(result.fixture_delete_response_accepted)
        self.assertFalse(result.fixture_target_absent_after_delete)

    def test_delete_response_must_match_official_nested_true(self):
        invalid = (
            None,
            {},
            {"result": True},
            {"result": {"result": False}},
            {"result": {"result": 1}},
            {"result": {"result": True, "unexpected": True}},
        )

        for response in invalid:
            with self.subTest(response=response):
                result = verify(delete_response=response)
                self.assertEqual(
                    result.reason,
                    "reply_rollback_delete_response_invalid",
                )

    def test_history_identity_must_remain_exact(self):
        for current in (
            history(chat_id=999),
            history(session_id=999),
        ):
            with self.subTest(identity=current["result"]):
                result = verify(current_history=current)
                self.assertEqual(
                    result.reason,
                    "reply_rollback_history_identity_mismatch",
                )

    def test_history_message_map_is_strict_and_unambiguous(self):
        invalid = (
            {"result": {"chatId": 78733, "sessionId": 900}},
            history(messages=[]),
            history(messages={"x": {"id": 701}}),
            history(messages={"701": {"id": 702}}),
            history(messages={"701": "private fixture"}),
        )

        for current in invalid:
            with self.subTest(current=current):
                result = verify(current_history=current)
                self.assertEqual(
                    result.reason,
                    "reply_rollback_history_response_invalid",
                )

    def test_public_result_is_fixture_only_and_redacted(self):
        result = verify()
        rendered = result.model_dump_json()

        for forbidden in (
            "78733",
            "373259",
            str(SENT_ID),
            "fixture humano",
            "fixture bot previo",
            "messageId",
            "chatId",
            "sessionId",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(result.fixture_only)
        self.assertFalse(result.real_rollback_composed)
        self.assertFalse(result.real_rollback_executed)
        self.assertFalse(result.real_portal_behavior_verified)
        self.assertEqual(result.external_calls, 0)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_models_are_frozen_strict_and_positive(self):
        preview = build_reply_rollback_delete_preview(
            bot_id=373259,
            sent_message_id=SENT_ID,
        )

        with self.assertRaises(ValidationError):
            ReplyRollbackDeletePreview.model_validate(
                {**preview.model_dump(), "complete": False}
            )
        with self.assertRaises(ValidationError):
            ReplyRollbackDeletePreview.model_validate(
                {**preview.model_dump(), "messageId": 0}
            )
        with self.assertRaises(ValidationError):
            ReplyRollbackDeletePreview.model_validate(
                {**preview.model_dump(), "auth": "forbidden"}
            )
        with self.assertRaises(ValidationError):
            preview.complete = False

    def test_source_has_no_client_io_auth_or_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_reply_rollback_contract.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "bitrixclient(",
            ".open(",
            "dotenv",
            "auth=",
            "access_token",
            "os.environ",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "asyncio",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
