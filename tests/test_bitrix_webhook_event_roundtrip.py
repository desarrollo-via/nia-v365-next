import unittest

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from bitrix_connector.bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripStatus,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.bitrix_webhook_event_roundtrip import (
    run_exact_controlled_webhook_event_roundtrip_with_rollback,
)
from bitrix_connector.models import NormalizedBitrixEvent
from bitrix_connector.nia_client import NiaChatResponse, NiaClientResult


def event(**changes):
    values = {
        "event": "ONIMBOTV2MESSAGEADD",
        "timestamp": 1772093963,
        "bot_id": 373259,
        "message_id": 9001,
        "chat_id": 78733,
        "dialog_id": "chat78733",
        "author_id": 27,
        "text": "mensaje humano fixture",
        "is_system": False,
        "user_id": 27,
        "user_is_bot": False,
        "user_is_connector": True,
        "domain": "portal.bitrix24.test",
        "member_id": "member-123",
    }
    values.update(changes)
    return NormalizedBitrixEvent.model_validate(values)


def preflight(*, baseline=9001):
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.READY,
            reason="bitrix_history_preflight_ready",
            dialog_read_calls=1,
            history_read_calls=0,
            dialog_verified=True,
            session_verified=True,
            baseline_captured=True,
            resources_closed=True,
        ),
        BitrixHistoryR0Anchor(700, baseline),
    )


class Recorder:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def send_approved_text(self, payload):
        self.calls.append(payload)
        return self.response

    async def send_approved_message(self, payload):
        self.calls.append(payload)
        return self.response


class History:
    def __init__(self, *, reply_present):
        self.reply_present = reply_present
        self.calls = []

    def response(self):
        messages = {"9001": {"id": 9001}}
        if self.reply_present:
            messages["9100"] = {"id": 9100}
        return {
            "result": {"chatId": 78733, "sessionId": 700, "message": messages}
        }

    async def read_post_send_history(self, *, session_id):
        self.calls.append(session_id)
        return self.response()

    async def read_post_delete_history(self, *, session_id):
        self.calls.append(session_id)
        return self.response()


class Deleter:
    def __init__(self):
        self.calls = []

    async def delete_approved_reply(self, preview):
        self.calls.append(preview)
        return {"result": {"result": True}}


def dependencies(*, reply_present=True):
    nia = Recorder(
        NiaClientResult.succeeded(
            NiaChatResponse(respuesta="respuesta fixture"), http_status=200
        )
    )
    bitrix = Recorder(
        BitrixClientResult.succeeded(
            BitrixSendResponse.model_validate({"result": {"id": 9100}}),
            http_status=200,
        )
    )
    return nia, bitrix, History(reply_present=reply_present), Deleter(), History(reply_present=False)


class WebhookEventRoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_event_reaches_nia_and_same_dialog_then_is_verified(self):
        nia, bitrix, post_send, deleter, post_delete = dependencies()
        result = await run_exact_controlled_webhook_event_roundtrip_with_rollback(
            plan=build_protected_real_roundtrip_plan(),
            preflight=preflight(),
            event=event(),
            nia_sender=nia,
            bitrix_sender=bitrix,
            post_send_history_reader=post_send,
            deleter=deleter,
            post_delete_history_reader=post_delete,
        )
        self.assertEqual(result.status, ComposedRoundtripStatus.VERIFIED)
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(len(bitrix.calls), 1)
        self.assertEqual(bitrix.calls[0].botId, 373259)
        self.assertEqual(bitrix.calls[0].dialogId, "chat78733")
        self.assertEqual(deleter.calls, [])

    async def test_post_send_failure_deletes_only_receipt_and_reverifies(self):
        nia, bitrix, post_send, deleter, post_delete = dependencies(
            reply_present=False
        )
        result = await run_exact_controlled_webhook_event_roundtrip_with_rollback(
            plan=build_protected_real_roundtrip_plan(),
            preflight=preflight(),
            event=event(),
            nia_sender=nia,
            bitrix_sender=bitrix,
            post_send_history_reader=post_send,
            deleter=deleter,
            post_delete_history_reader=post_delete,
        )
        self.assertEqual(result.status, ComposedRoundtripStatus.ROLLED_BACK)
        self.assertEqual(len(deleter.calls), 1)
        self.assertEqual(deleter.calls[0].messageId, 9100)
        self.assertEqual(post_delete.calls, [700])

    async def test_identity_or_anchor_drift_stops_before_calls(self):
        cases = (
            event(chat_id=78734, dialog_id="chat78734"),
            event(bot_id=245339),
            event(user_is_connector=False),
            event(is_system=True),
        )
        for candidate in cases:
            nia, bitrix, post_send, deleter, post_delete = dependencies()
            with self.subTest(candidate=candidate.model_dump(exclude={"text"})):
                with self.assertRaises(ValueError):
                    await run_exact_controlled_webhook_event_roundtrip_with_rollback(
                        plan=build_protected_real_roundtrip_plan(),
                        preflight=preflight(),
                        event=candidate,
                        nia_sender=nia,
                        bitrix_sender=bitrix,
                        post_send_history_reader=post_send,
                        deleter=deleter,
                        post_delete_history_reader=post_delete,
                    )
                self.assertEqual(nia.calls, [])
                self.assertEqual(bitrix.calls, [])
        nia, bitrix, post_send, deleter, post_delete = dependencies()
        with self.assertRaisesRegex(ValueError, "webhook_event_anchor_mismatch"):
            await run_exact_controlled_webhook_event_roundtrip_with_rollback(
                plan=build_protected_real_roundtrip_plan(),
                preflight=preflight(baseline=9000),
                event=event(),
                nia_sender=nia,
                bitrix_sender=bitrix,
                post_send_history_reader=post_send,
                deleter=deleter,
                post_delete_history_reader=post_delete,
            )
        self.assertEqual(nia.calls, [])
        self.assertEqual(bitrix.calls, [])


if __name__ == "__main__":
    unittest.main()
