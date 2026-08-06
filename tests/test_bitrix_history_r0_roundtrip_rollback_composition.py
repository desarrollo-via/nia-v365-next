import unittest
from pathlib import Path

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from bitrix_connector.bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripStatus,
    run_composed_roundtrip_with_rollback,
)
from bitrix_connector.nia_client import NiaChatResponse, NiaClientResult


ROOT = Path(__file__).resolve().parents[1]
SENT_ID = 800


def inbound_payload():
    return {
        "result": {
            "chatId": 78733,
            "sessionId": 900,
            "message": [
                {
                    "id": 701,
                    "chatid": 78733,
                    "senderid": 51,
                    "recipientid": "chat78733",
                    "date": "2026-08-03T15:00:01+00:00",
                    "text": "mensaje humano fixture",
                }
            ],
            "users": [{"id": 51, "connector": True}],
        }
    }


def history(*, include_reply):
    messages = {"701": {"id": 701}}
    if include_reply:
        messages[str(SENT_ID)] = {"id": SENT_ID}
    return {
        "result": {
            "chatId": 78733,
            "sessionId": 900,
            "message": messages,
        }
    }


class FakeNiaSender:
    def __init__(self):
        self.calls = []

    async def send_approved_text(self, payload):
        self.calls.append(payload)
        return NiaClientResult.succeeded(
            NiaChatResponse(respuesta="respuesta nia fixture"),
            http_status=200,
        )


class FakeBitrixSender:
    def __init__(self):
        self.calls = []

    async def send_approved_message(self, payload):
        self.calls.append(payload)
        return BitrixClientResult.succeeded(
            BitrixSendResponse.model_validate({"result": {"id": SENT_ID}}),
            http_status=200,
        )


class FakePostSendReader:
    def __init__(self, response=None, error=None):
        self.response = history(include_reply=True) if response is None else response
        self.error = error
        self.calls = []

    async def read_post_send_history(self, *, session_id):
        self.calls.append(session_id)
        if self.error:
            raise self.error
        return self.response


class FakeDeleter:
    def __init__(self, response=None):
        self.response = {"result": {"result": True}} if response is None else response
        self.calls = []

    async def delete_approved_reply(self, preview):
        self.calls.append(preview)
        return self.response


class FakePostDeleteReader:
    def __init__(self, response=None):
        self.response = history(include_reply=False) if response is None else response
        self.calls = []

    async def read_post_delete_history(self, *, session_id):
        self.calls.append(session_id)
        return self.response


async def run(*, post_send=None, deleter=None, post_delete=None, emergency=False):
    nia = FakeNiaSender()
    bitrix = FakeBitrixSender()
    post_send = post_send or FakePostSendReader()
    deleter = deleter or FakeDeleter()
    post_delete = post_delete or FakePostDeleteReader()
    result = await run_composed_roundtrip_with_rollback(
        plan=build_protected_real_roundtrip_plan(),
        payload=inbound_payload(),
        expected_chat_id=78733,
        expected_dialog_id="chat78733",
        expected_session_id=900,
        expected_sender_id=51,
        baseline_message_id=700,
        controlled_bot_id=373259,
        nia_sender=nia,
        bitrix_sender=bitrix,
        post_send_history_reader=post_send,
        deleter=deleter,
        post_delete_history_reader=post_delete,
        emergency_rollback=emergency,
    )
    return result, nia, bitrix, post_send, deleter, post_delete


class ComposedRoundtripRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_reply_is_preserved_without_rollback(self):
        result, nia, bitrix, post_send, deleter, post_delete = await run()

        self.assertEqual(result.status, ComposedRoundtripStatus.VERIFIED)
        self.assertTrue(result.exact_send_receipt_obtained)
        self.assertTrue(result.fixture_reply_present_same_session)
        self.assertTrue(result.fixture_reply_preserved)
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(len(bitrix.calls), 1)
        self.assertEqual(post_send.calls, [900])
        self.assertEqual(deleter.calls, [])
        self.assertEqual(post_delete.calls, [])

    async def test_ambiguous_post_send_history_rolls_back_exact_receipt(self):
        result, _, _, post_send, deleter, post_delete = await run(
            post_send=FakePostSendReader(response=history(include_reply=False))
        )

        self.assertEqual(result.status, ComposedRoundtripStatus.ROLLED_BACK)
        self.assertEqual(
            result.reason,
            "composed_post_send_verification_failed_rollback_verified",
        )
        self.assertEqual(post_send.calls, [900])
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(deleter.calls[0].messageId, SENT_ID)
        self.assertEqual(post_delete.calls, [900])
        self.assertTrue(result.fixture_rollback_verified)

    async def test_post_send_exception_is_redacted_and_rolls_back(self):
        result, _, _, _, deleter, _ = await run(
            post_send=FakePostSendReader(error=RuntimeError("private fixture"))
        )

        self.assertEqual(result.status, ComposedRoundtripStatus.ROLLED_BACK)
        self.assertEqual(len(deleter.calls), 1)
        self.assertNotIn("private fixture", result.model_dump_json())

    async def test_emergency_uses_same_receipt_once_even_after_verification(self):
        result, _, _, _, deleter, post_delete = await run(emergency=True)

        self.assertEqual(result.status, ComposedRoundtripStatus.ROLLED_BACK)
        self.assertEqual(result.reason, "composed_emergency_rollback_verified")
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(deleter.calls[0].messageId, SENT_ID)
        self.assertEqual(len(post_delete.calls), 1)
        self.assertTrue(result.emergency_rollback_requested)

    async def test_failed_rollback_remains_no_go_without_retry(self):
        result, _, _, _, deleter, post_delete = await run(
            post_send=FakePostSendReader(response={"result": {}}),
            deleter=FakeDeleter(response={"result": {"result": False}}),
        )

        self.assertEqual(result.status, ComposedRoundtripStatus.NO_GO)
        self.assertEqual(result.reason, "composed_required_rollback_failed")
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(post_delete.calls, [])

    async def test_public_result_is_redacted_and_fixture_only(self):
        result, *_ = await run()
        rendered = result.model_dump_json()
        for forbidden in (
            "78733",
            "373259",
            str(SENT_ID),
            "mensaje humano",
            "respuesta nia",
            "payload",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(result.fixture_only)
        self.assertFalse(result.real_execution_authorized)
        self.assertFalse(result.real_roundtrip_executed)
        self.assertEqual(result.external_calls, 0)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    async def test_missing_dependency_fails_before_calls(self):
        with self.assertRaises(ValueError):
            await run_composed_roundtrip_with_rollback(
                plan=build_protected_real_roundtrip_plan(),
                payload=inbound_payload(),
                expected_chat_id=78733,
                expected_dialog_id="chat78733",
                expected_session_id=900,
                baseline_message_id=700,
                controlled_bot_id=373259,
                nia_sender=FakeNiaSender(),
                bitrix_sender=FakeBitrixSender(),
                post_send_history_reader=None,
                deleter=FakeDeleter(),
                post_delete_history_reader=FakePostDeleteReader(),
            )

    def test_source_has_no_real_client_auth_io_cli_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_roundtrip_rollback_composition.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "niaclient(",
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
