import unittest
from pathlib import Path

from bitrix_connector.bitrix_client import (
    BitrixClientDecision,
    BitrixClientResult,
    BitrixSendResponse,
)
from bitrix_connector.bitrix_history_r0_isolated_roundtrip import (
    IsolatedRoundtripStatus,
    run_isolated_history_nia_bitrix_roundtrip,
)
from bitrix_connector.nia_client import (
    NiaChatResponse,
    NiaClientDecision,
    NiaClientResult,
)


ROOT = Path(__file__).resolve().parents[1]
HUMAN_TEXT = "mensaje humano fixture para conexion"
NIA_TEXT = "respuesta nia fixture para el chat"


def payload(*, messages=None):
    return {
        "result": {
            "chatId": 78733,
            "sessionId": 900,
            "message": messages
            if messages is not None
            else [
                {
                    "id": 701,
                    "chatid": 78733,
                    "senderid": 51,
                    "recipientid": "chat78733",
                    "date": "2026-08-03T15:00:01+00:00",
                    "text": HUMAN_TEXT,
                },
                {"senderId": 245339, "text": None},
            ],
            "users": [
                {"id": 51, "connector": True},
                {"id": 245339, "connector": False},
            ],
        }
    }


class FakeNiaSender:
    def __init__(self, result=None, error=None):
        self.result = result or NiaClientResult.succeeded(
            NiaChatResponse(respuesta=NIA_TEXT),
            http_status=200,
        )
        self.error = error
        self.calls = []

    async def send_approved_text(self, current):
        self.calls.append(current)
        if self.error:
            raise self.error
        return self.result


class FakeBitrixSender:
    def __init__(self, result=None, error=None):
        self.result = result or BitrixClientResult.succeeded(
            BitrixSendResponse.model_validate({"result": {"id": 800}}),
            http_status=200,
        )
        self.error = error
        self.calls = []

    async def send_approved_message(self, current):
        self.calls.append(current)
        if self.error:
            raise self.error
        return self.result


async def run(current_payload, nia=None, bitrix=None):
    nia = nia or FakeNiaSender()
    bitrix = bitrix or FakeBitrixSender()
    result = await run_isolated_history_nia_bitrix_roundtrip(
        payload=current_payload,
        expected_chat_id=78733,
        expected_dialog_id="chat78733",
        expected_session_id=900,
        expected_sender_id=51,
        baseline_message_id=700,
        controlled_bot_id=373259,
        nia_sender=nia,
        bitrix_sender=bitrix,
    )
    return result, nia, bitrix


class IsolatedHistoryNiaBitrixRoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_message_reaches_nia_and_response_returns_to_same_chat(self):
        result, nia, bitrix = await run(payload())

        self.assertEqual(result.status, IsolatedRoundtripStatus.VERIFIED)
        self.assertEqual(result.nia_call_count, 1)
        self.assertEqual(result.bitrix_reply_call_count, 1)
        self.assertTrue(result.fixture_nia_received)
        self.assertTrue(result.fixture_bitrix_reply_sent)
        self.assertTrue(result.same_controlled_dialog_preserved)
        self.assertEqual(nia.calls[0].mensaje, HUMAN_TEXT)
        self.assertEqual(nia.calls[0].session_id, "bitrix:900:chat78733")
        self.assertEqual(bitrix.calls[0].botId, 373259)
        self.assertEqual(bitrix.calls[0].dialogId, "chat78733")
        self.assertEqual(bitrix.calls[0].fields.message, NIA_TEXT)

    async def test_minimum_filter_does_not_require_hash_or_window(self):
        result, _, _ = await run(payload())

        self.assertTrue(result.minimum_filter_only)
        self.assertFalse(result.exact_text_filter_required)

    async def test_invalid_history_stops_before_nia_and_bitrix(self):
        broken = payload()
        broken["result"]["message"] = "invalid"

        result, nia, bitrix = await run(broken)

        self.assertEqual(result.status, IsolatedRoundtripStatus.NO_GO)
        self.assertEqual(result.reason, "isolated_history_invalid")
        self.assertEqual(
            result.failure_category,
            "reader_history_collections_invalid",
        )
        self.assertEqual(nia.calls, [])
        self.assertEqual(bitrix.calls, [])

    async def test_zero_or_multiple_humans_stop_before_nia(self):
        zero = payload(messages=[{"senderId": 245339}])
        duplicate = payload(
            messages=[
                payload()["result"]["message"][0],
                {
                    **payload()["result"]["message"][0],
                    "id": 702,
                    "text": "segundo humano fixture",
                },
            ]
        )

        for current in (zero, duplicate):
            with self.subTest(count=len(current["result"]["message"])):
                result, nia, bitrix = await run(current)
                self.assertEqual(
                    result.reason,
                    "isolated_human_candidate_count_invalid",
                )
                self.assertEqual(nia.calls, [])
                self.assertEqual(bitrix.calls, [])

    async def test_nia_failure_or_invalid_response_never_calls_bitrix(self):
        cases = (
            FakeNiaSender(
                result=NiaClientResult.failed("fixture_nia_failed")
            ),
            FakeNiaSender(
                result=NiaClientResult.succeeded(
                    NiaChatResponse(respuesta=" "),
                    http_status=200,
                )
            ),
            FakeNiaSender(
                result=NiaClientResult.succeeded(
                    NiaChatResponse(respuesta="x" * 20_001),
                    http_status=200,
                )
            ),
        )
        for nia in cases:
            with self.subTest(decision=nia.result.decision):
                result, _, bitrix = await run(payload(), nia=nia)
                self.assertEqual(result.status, IsolatedRoundtripStatus.NO_GO)
                self.assertEqual(result.nia_call_count, 1)
                self.assertEqual(bitrix.calls, [])

    async def test_bitrix_failure_is_terminal_without_retry(self):
        bitrix = FakeBitrixSender(
            result=BitrixClientResult(
                decision=BitrixClientDecision.FAIL,
                error_code="fixture_bitrix_failed",
            )
        )

        result, nia, bitrix = await run(payload(), bitrix=bitrix)

        self.assertEqual(result.reason, "isolated_bitrix_reply_failed")
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(len(bitrix.calls), 1)
        self.assertEqual(result.bitrix_reply_call_count, 1)

    async def test_dependency_exception_is_redacted_and_not_retried(self):
        nia = FakeNiaSender(error=RuntimeError("contenido privado fixture"))

        result, nia, bitrix = await run(payload(), nia=nia)

        self.assertEqual(result.reason, "isolated_roundtrip_failed")
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(bitrix.calls, [])
        self.assertNotIn("contenido privado", result.model_dump_json())

    async def test_public_result_distinguishes_fixture_from_real_effects(self):
        result, _, _ = await run(payload())
        rendered = result.model_dump_json()

        for forbidden in (
            HUMAN_TEXT,
            NIA_TEXT,
            "78733",
            "900",
            "373259",
            "245339",
            "sender",
            "payload",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(result.fixture_only)
        self.assertFalse(result.actual_connection_proven)
        self.assertEqual(result.external_calls, 0)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_source_has_no_real_clients_io_wait_or_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_isolated_roundtrip.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "niaclient(",
            "bitrixclient(",
            ".open(",
            "dotenv",
            "os.environ",
            "get_dialog(",
            "get_session_history(",
            "sleep(",
            "waiting-message",
            "input(",
            "asyncio.run",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
