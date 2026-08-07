import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_reply_rollback_adapter import (
    InjectedReplyRollbackStatus,
    run_injected_reply_rollback,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)


ROOT = Path(__file__).resolve().parents[1]
SENT_ID = 800


def valid_history(*, include_target=False):
    messages = {"701": {"id": 701}}
    if include_target:
        messages[str(SENT_ID)] = {"id": SENT_ID}
    return {
        "result": {
            "chatId": 78733,
            "sessionId": 900,
            "message": messages,
        }
    }


class FakeDeleter:
    def __init__(self, response=None, error=None):
        self.response = (
            {"result": {"result": True}}
            if response is None
            else response
        )
        self.error = error
        self.calls = []

    async def delete_approved_reply(self, preview):
        self.calls.append(preview)
        if self.error:
            raise self.error
        return self.response


class FakeHistoryReader:
    def __init__(self, response=None, error=None):
        self.response = valid_history() if response is None else response
        self.error = error
        self.calls = []

    async def read_post_delete_history(self, *, session_id):
        self.calls.append(session_id)
        if self.error:
            raise self.error
        return self.response


async def run(deleter=None, reader=None):
    deleter = deleter or FakeDeleter()
    reader = reader or FakeHistoryReader()
    result = await run_injected_reply_rollback(
        plan=build_protected_real_roundtrip_plan(),
        controlled_bot_id=373259,
        sent_message_id=SENT_ID,
        expected_chat_id=78733,
        expected_session_id=900,
        deleter=deleter,
        history_reader=reader,
    )
    return result, deleter, reader


class InjectedReplyRollbackAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_uses_exact_id_then_verifies_same_session_absence(self):
        result, deleter, reader = await run()

        self.assertEqual(result.status, InjectedReplyRollbackStatus.VERIFIED)
        self.assertEqual(result.delete_call_count, 1)
        self.assertEqual(result.history_read_call_count, 1)
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(deleter.calls[0].botId, 373259)
        self.assertEqual(deleter.calls[0].messageId, SENT_ID)
        self.assertTrue(deleter.calls[0].complete)
        self.assertEqual(reader.calls, [900])
        self.assertTrue(result.fixture_absence_verified)

    async def test_invalid_delete_receipt_stops_before_history(self):
        deleter = FakeDeleter(response={"result": {"result": False}})

        result, deleter, reader = await run(deleter=deleter)

        self.assertEqual(
            result.reason,
            "injected_reply_delete_response_invalid",
        )
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(reader.calls, [])

    async def test_delete_exception_is_redacted_and_not_retried(self):
        deleter = FakeDeleter(error=RuntimeError("secret fixture"))

        result, deleter, reader = await run(deleter=deleter)

        self.assertEqual(result.reason, "injected_reply_delete_failed")
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(reader.calls, [])
        self.assertNotIn("secret fixture", result.model_dump_json())

    async def test_history_exception_is_terminal_after_one_read(self):
        reader = FakeHistoryReader(error=RuntimeError("private history"))

        result, deleter, reader = await run(reader=reader)

        self.assertEqual(result.reason, "injected_reply_history_read_failed")
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(len(reader.calls), 1)
        self.assertNotIn("private history", result.model_dump_json())

    async def test_present_target_or_wrong_identity_is_no_go(self):
        cases = (
            (
                valid_history(include_target=True),
                "reply_rollback_target_still_present",
            ),
            (
                {
                    "result": {
                        "chatId": 999,
                        "sessionId": 900,
                        "message": {},
                    }
                },
                "reply_rollback_history_identity_mismatch",
            ),
        )
        for response, reason in cases:
            with self.subTest(reason=reason):
                result, deleter, reader = await run(
                    reader=FakeHistoryReader(response=response)
                )
                self.assertEqual(
                    result.reason,
                    "injected_reply_rollback_verification_failed",
                )
                self.assertEqual(result.verification_failure_reason, reason)
                self.assertEqual(len(deleter.calls), 1)
                self.assertEqual(len(reader.calls), 1)

    async def test_public_result_distinguishes_fixture_from_real_rollback(self):
        result, _, _ = await run()
        rendered = result.model_dump_json()

        for forbidden in (
            "78733",
            "373259",
            str(SENT_ID),
            "chatId",
            "sessionId",
            "messageId",
            "payload",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(result.dependencies_injected)
        self.assertTrue(result.real_ready_contract)
        self.assertTrue(result.m56_blocked_plan_applied)
        self.assertTrue(result.fixture_only)
        self.assertFalse(result.command_available)
        self.assertFalse(result.cli_available)
        self.assertFalse(result.source_bound)
        self.assertFalse(result.authorization_present)
        self.assertFalse(result.real_execution_authorized)
        self.assertFalse(result.real_rollback_executed)
        self.assertFalse(result.real_portal_behavior_verified)
        self.assertEqual(result.external_calls, 0)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    async def test_missing_dependencies_fail_before_any_call(self):
        with self.assertRaises(ValueError):
            await run_injected_reply_rollback(
                plan=build_protected_real_roundtrip_plan(),
                controlled_bot_id=373259,
                sent_message_id=SENT_ID,
                expected_chat_id=78733,
                expected_session_id=900,
                deleter=None,
                history_reader=FakeHistoryReader(),
            )

    def test_source_has_no_real_client_auth_io_cli_or_retry_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_reply_rollback_adapter.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "bitrixclient(",
            ".open(",
            "dotenv",
            "access_token",
            "os.environ",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "asyncio.run",
            "sleep(",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
