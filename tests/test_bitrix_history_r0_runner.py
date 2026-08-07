import asyncio
import hashlib
import unittest
from datetime import datetime, timezone

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
    BitrixSessionHistory,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Status,
    execute_bitrix_history_r0_once,
)
from bitrix_connector.config import load_settings


MESSAGE_TEXT = "mensaje controlado único"
MESSAGE_HASH = hashlib.sha256(MESSAGE_TEXT.encode("utf-8")).hexdigest()
WINDOW_START = datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)


def dialog(last_message_id=700, session_id=900):
    return BitrixHistoryDialog.model_validate({
        "id": 78733,
        "dialog_id": "chat78733",
        "entity_type": "LINES",
        "entity_data_1": f"a|b|c|d|e|{session_id}",
        "role": "guest",
        "last_message_id": last_message_id,
    })


def history():
    return BitrixSessionHistory.model_validate({
        "chatId": 78733,
        "sessionId": 900,
        "message": [{
            "id": 701,
            "chatid": 78733,
            "senderid": 51,
            "recipientid": "chat78733",
            "date": "2026-07-31T15:00:01+00:00",
            "text": MESSAGE_TEXT,
        }],
        "users": [{"id": 51, "connector": True}],
    })


class FakeHistoryClient:
    def __init__(self, dialogs, history_result=None, close_error=False):
        self.dialogs = list(dialogs)
        self.history_result = history_result
        self.dialog_calls = 0
        self.history_calls = 0
        self.closed = False
        self.close_error = close_error

    async def get_dialog(self, dialog_id):
        self.dialog_calls += 1
        current = self.dialogs.pop(0)
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.SUCCESS,
            dialog=current,
            http_status=200,
        )

    async def get_session_history(self, session_id):
        self.history_calls += 1
        return self.history_result

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("close failed")


async def no_sleep(_seconds):
    return None


class BitrixHistoryR0RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_receives_once_with_inert_output_and_closed_resources(self):
        history_result = BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.SUCCESS,
            history=history(),
            http_status=200,
        )
        client = FakeHistoryClient([dialog(), dialog(701)], history_result)

        result = await execute_bitrix_history_r0_once(
            client=client,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            expected_text_sha256=MESSAGE_HASH,
            window_start=WINDOW_START,
            wait_seconds=10,
            poll_seconds=5,
            sleep=no_sleep,
        )

        self.assertEqual(result.status, BitrixHistoryR0Status.RECEIVED)
        self.assertEqual(client.dialog_calls, 2)
        self.assertEqual(client.history_calls, 1)
        self.assertTrue(client.closed)
        self.assertEqual(result.mutation_calls, 0)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_called)
        self.assertFalse(result.bitrix_written)
        self.assertTrue(result.resources_closed)
        self.assertEqual(set(result.model_dump()), {
            "status", "reason", "dialog_read_calls", "history_read_calls",
            "mutation_calls", "dialog_verified", "session_verified",
            "baseline_captured", "new_last_message_detected",
            "candidate_count", "controlled_message_verified",
            "connector_locked_off", "persisted", "nia_called",
            "bitrix_written", "resources_closed",
        })

    async def test_timeout_never_reads_history(self):
        client = FakeHistoryClient([dialog(), dialog(), dialog()])
        result = await execute_bitrix_history_r0_once(
            client=client,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            expected_text_sha256=MESSAGE_HASH,
            window_start=WINDOW_START,
            wait_seconds=10,
            poll_seconds=5,
            sleep=no_sleep,
        )
        self.assertEqual(result.status, BitrixHistoryR0Status.NO_GO)
        self.assertEqual(result.reason, "bitrix_history_wait_timeout")
        self.assertEqual(client.dialog_calls, 3)
        self.assertEqual(client.history_calls, 0)
        self.assertTrue(result.resources_closed)

    async def test_degraded_barrier_fails_before_reads(self):
        client = FakeHistoryClient([])
        settings = load_settings({
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_PILOT_ENABLED": "true",
            "NIA_BITRIX_PILOT_EMERGENCY_STOP": "false",
            "NIA_BITRIX_PILOT_RULES_JSON": "[]",
        })
        result = await execute_bitrix_history_r0_once(
            client=client,
            settings=settings,
            expected_text_sha256=MESSAGE_HASH,
            window_start=WINDOW_START,
            sleep=no_sleep,
        )
        self.assertEqual(result.reason, "bitrix_history_barrier_degraded")
        self.assertEqual(client.dialog_calls, 0)
        self.assertEqual(client.history_calls, 0)
        self.assertTrue(client.closed)

    async def test_session_drift_and_close_failure_are_terminal(self):
        client = FakeHistoryClient(
            [dialog(), dialog(701, session_id=901)],
            close_error=True,
        )
        result = await execute_bitrix_history_r0_once(
            client=client,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            expected_text_sha256=MESSAGE_HASH,
            window_start=WINDOW_START,
            wait_seconds=10,
            poll_seconds=5,
            sleep=no_sleep,
        )
        self.assertEqual(result.status, BitrixHistoryR0Status.NO_GO)
        self.assertEqual(result.reason, "bitrix_history_resources_close_failed")
        self.assertFalse(result.resources_closed)
        self.assertEqual(client.history_calls, 0)

    async def test_cancellation_still_closes_resources(self):
        client = FakeHistoryClient([dialog()])

        async def cancel_sleep(_seconds):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await execute_bitrix_history_r0_once(
                client=client,
                settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                expected_text_sha256=MESSAGE_HASH,
                window_start=WINDOW_START,
                sleep=cancel_sleep,
            )
        self.assertTrue(client.closed)
        self.assertEqual(client.history_calls, 0)


if __name__ == "__main__":
    unittest.main()
