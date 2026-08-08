import inspect
import unittest
from copy import deepcopy

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_history_r0_exact_scope_composition import (
    run_exact_controlled_roundtrip_with_rollback,
)
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
from bitrix_connector.nia_client import NiaChatResponse, NiaClientResult


def ready_preflight(*, session_id=900, baseline_message_id=700):
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
        BitrixHistoryR0Anchor(session_id, baseline_message_id),
    )


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


class HistoryReader:
    def __init__(self, include_reply=True):
        self.include_reply = include_reply
        self.calls = []

    def _response(self):
        messages = {"701": {"id": 701}}
        if self.include_reply:
            messages["800"] = {"id": 800}
        return {
            "result": {
                "chatId": 78733,
                "sessionId": 900,
                "message": messages,
            }
        }

    async def read_post_send_history(self, *, session_id):
        self.calls.append(session_id)
        return self._response()

    async def read_post_delete_history(self, *, session_id):
        self.calls.append(session_id)
        return self._response()


class Deleter:
    def __init__(self):
        self.calls = []

    async def delete_approved_reply(self, payload):
        self.calls.append(payload)
        return {"result": {"result": True}}


def dependencies():
    nia = Recorder(
        NiaClientResult.succeeded(
            NiaChatResponse(respuesta="respuesta fixture"), http_status=200
        )
    )
    bitrix = Recorder(
        BitrixClientResult.succeeded(
            BitrixSendResponse.model_validate({"result": {"id": 800}}),
            http_status=200,
        )
    )
    return nia, bitrix, HistoryReader(), Deleter(), HistoryReader(False)


async def execute(payload, *, preflight=None):
    nia, bitrix, post_send, deleter, post_delete = dependencies()
    result = await run_exact_controlled_roundtrip_with_rollback(
        plan=build_protected_real_roundtrip_plan(),
        preflight=preflight or ready_preflight(),
        payload=payload,
        expected_sender_id=51,
        nia_sender=nia,
        bitrix_sender=bitrix,
        post_send_history_reader=post_send,
        deleter=deleter,
        post_delete_history_reader=post_delete,
    )
    return result, nia, bitrix, post_send, deleter, post_delete


class ExactScopeCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_controlled_scope_reaches_nia_and_bitrix(self):
        result, nia, bitrix, post_send, deleter, post_delete = await execute(
            inbound_payload()
        )

        self.assertEqual(result.status, ComposedRoundtripStatus.VERIFIED)
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(len(bitrix.calls), 1)
        self.assertEqual(bitrix.calls[0].botId, 373259)
        self.assertEqual(bitrix.calls[0].dialogId, "chat78733")
        self.assertEqual(post_send.calls, [900])
        self.assertEqual(deleter.calls, [])
        self.assertEqual(post_delete.calls, [])

    async def test_other_or_mixed_identity_stops_before_nia_and_bitrix(self):
        mutations = (
            ("chat", 99999),
            ("session", 901),
            ("message_chat", 99999),
            ("dialog", "chat99999"),
        )
        for kind, value in mutations:
            with self.subTest(kind=kind):
                payload = deepcopy(inbound_payload())
                if kind == "chat":
                    payload["result"]["chatId"] = value
                elif kind == "session":
                    payload["result"]["sessionId"] = value
                elif kind == "message_chat":
                    payload["result"]["message"][0]["chatid"] = value
                else:
                    payload["result"]["message"][0]["recipientid"] = value
                result, nia, bitrix, post_send, deleter, post_delete = (
                    await execute(payload)
                )
                self.assertEqual(result.status, ComposedRoundtripStatus.NO_GO)
                self.assertEqual(nia.calls, [])
                self.assertEqual(bitrix.calls, [])
                self.assertEqual(post_send.calls, [])
                self.assertEqual(deleter.calls, [])
                self.assertEqual(post_delete.calls, [])

    async def test_session_must_match_anchor_derived_from_preflight(self):
        result, nia, bitrix, post_send, deleter, post_delete = await execute(
            inbound_payload(), preflight=ready_preflight(session_id=901)
        )

        self.assertEqual(result.status, ComposedRoundtripStatus.NO_GO)
        self.assertEqual(nia.calls, [])
        self.assertEqual(bitrix.calls, [])
        self.assertEqual(post_send.calls, [])
        self.assertEqual(deleter.calls, [])
        self.assertEqual(post_delete.calls, [])

    async def test_non_ready_preflight_fails_before_all_dependencies(self):
        nia, bitrix, post_send, deleter, post_delete = dependencies()
        invalid = BitrixHistoryR0PreflightOutcome(
            BitrixHistoryR0Result(
                status=BitrixHistoryR0Status.NO_GO,
                reason="fixture_no_go",
                dialog_read_calls=1,
                history_read_calls=0,
                resources_closed=True,
            )
        )
        with self.assertRaisesRegex(ValueError, "exact_scope_preflight_invalid"):
            await run_exact_controlled_roundtrip_with_rollback(
                plan=build_protected_real_roundtrip_plan(),
                preflight=invalid,
                payload=inbound_payload(),
                nia_sender=nia,
                bitrix_sender=bitrix,
                post_send_history_reader=post_send,
                deleter=deleter,
                post_delete_history_reader=post_delete,
            )
        for dependency in (nia, bitrix, post_send, deleter, post_delete):
            self.assertEqual(dependency.calls, [])

    def test_public_entrypoint_accepts_no_configurable_scope_ids(self):
        parameters = inspect.signature(
            run_exact_controlled_roundtrip_with_rollback
        ).parameters
        for forbidden in (
            "expected_chat_id",
            "expected_dialog_id",
            "expected_session_id",
            "baseline_message_id",
            "controlled_bot_id",
        ):
            self.assertNotIn(forbidden, parameters)


if __name__ == "__main__":
    unittest.main()
