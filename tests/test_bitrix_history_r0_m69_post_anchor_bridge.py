import unittest
from copy import deepcopy
from pathlib import Path

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_history_r0_m68_combined_preflight import (
    CombinedR1PreflightAdapter,
    InjectedClosedProbeResult,
)
from bitrix_connector.bitrix_history_r0_m69_post_anchor_bridge import (
    PostAnchorBridgeStatus,
    PostAnchorExactScopeBridge,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.bot_v2_preflight import BotV2PreflightResult, BotV2PreflightStatus
from bitrix_connector.nia_client import NiaChatResponse, NiaClientResult
from bitrix_connector.openline_pilot_preflight import (
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
)


ROOT = Path(__file__).resolve().parents[1]


class Probe:
    def __init__(self, value):
        self.value = value

    async def __call__(self):
        return InjectedClosedProbeResult(self.value)


def ready_owner():
    config = OpenLineConfigSnapshot.model_validate(
        {
            "ID": 13,
            "LINE_NAME": "fixture",
            "ACTIVE": "Y",
            "WELCOME_BOT_ENABLE": "Y",
            "WELCOME_BOT_JOIN": "always",
            "WELCOME_BOT_ID": 245339,
            "WELCOME_BOT_TIME": 0,
            "WELCOME_BOT_LEFT": "close",
            "NO_ANSWER_BOT_ID": 0,
            "CLOSE_BOT_ID": 0,
            "AUTO_CLOSE_BOT_ID": 0,
            "WORKTIME_DAYOFF_BOT_ID": 0,
        }
    )
    owner = CombinedR1PreflightAdapter(
        bot_probe=Probe(
            BotV2PreflightResult(
                status=BotV2PreflightStatus.EXISTING_COMPATIBLE,
                reason="bot_v2_preflight_existing_compatible",
                rest_revision=35,
                existing_bot_id=373259,
                registration_needed=False,
            )
        ),
        openline_probe=Probe(
            OpenLinePreflightResult(
                status=OpenLinePreflightStatus.READY,
                reason="openline_snapshot_ready",
                chat_id=78733,
                dialog_id="chat78733",
                config=config,
            )
        ),
        history_probe=Probe(
            BitrixHistoryR0PreflightOutcome(
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
                BitrixHistoryR0Anchor(900, 700),
            )
        ),
    )
    return owner


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
                    "text": "texto privado fixture",
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


class PostAnchorReader:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def read_post_anchor_history(self, *, session_id):
        self.calls.append(session_id)
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


class HistoryReader:
    def __init__(self, include_reply=True):
        self.include_reply = include_reply
        self.calls = []

    def response(self):
        messages = {"701": {"id": 701}}
        if self.include_reply:
            messages["800"] = {"id": 800}
        return {"result": {"chatId": 78733, "sessionId": 900, "message": messages}}

    async def read_post_send_history(self, *, session_id):
        self.calls.append(session_id)
        return self.response()

    async def read_post_delete_history(self, *, session_id):
        self.calls.append(session_id)
        return self.response()


class Deleter:
    def __init__(self):
        self.calls = []

    async def delete_approved_reply(self, payload):
        self.calls.append(payload)
        return {"result": {"result": True}}


async def bridge_for(payload):
    owner = ready_owner()
    await owner.probe_once()
    history = PostAnchorReader(payload)
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
    post_send = HistoryReader()
    deleter = Deleter()
    post_delete = HistoryReader(False)
    bridge = PostAnchorExactScopeBridge(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=owner,
        history_reader=history,
        expected_sender_id=51,
        nia_sender=nia,
        bitrix_sender=bitrix,
        post_send_history_reader=post_send,
        deleter=deleter,
        post_delete_history_reader=post_delete,
    )
    return bridge, owner, history, nia, bitrix, post_send, deleter, post_delete


class PostAnchorExactScopeBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_m68_anchor_one_read_and_m62_exact_scope_are_linked(self):
        items = await bridge_for(inbound_payload())
        bridge, owner, history, nia, bitrix, post_send, deleter, post_delete = items

        result = await bridge.run_once()

        self.assertEqual(result.status, PostAnchorBridgeStatus.VERIFIED)
        self.assertEqual((result.history_read_count, result.exact_scope_call_count), (1, 1))
        self.assertEqual(history.calls, [900])
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(len(bitrix.calls), 1)
        self.assertEqual(post_send.calls, [900])
        self.assertEqual(deleter.calls, [])
        self.assertEqual(post_delete.calls, [])
        self.assertTrue(owner.cleared)
        self.assertTrue(bridge.cleared)
        self.assertNotIn("texto privado fixture", result.model_dump_json())

    async def test_invalid_or_ambiguous_history_stops_before_nia_and_bitrix(self):
        invalid = deepcopy(inbound_payload())
        invalid["result"]["chatId"] = 99999
        ambiguous = deepcopy(inbound_payload())
        duplicate = deepcopy(ambiguous["result"]["message"][0])
        duplicate["id"] = 702
        ambiguous["result"]["message"].append(duplicate)
        for payload in (invalid, ambiguous):
            with self.subTest(kind="invalid" if payload is invalid else "ambiguous"):
                items = await bridge_for(payload)
                bridge, _, history, nia, bitrix, post_send, deleter, post_delete = items
                result = await bridge.run_once()
                self.assertEqual(result.status, PostAnchorBridgeStatus.NO_GO)
                self.assertEqual(result.reason, "m69_exact_scope_no_go")
                self.assertEqual(history.calls, [900])
                for dependency in (nia, bitrix, post_send, deleter, post_delete):
                    self.assertEqual(dependency.calls, [])

    async def test_history_exception_is_safe_and_does_not_reach_m62(self):
        items = await bridge_for(RuntimeError("private response"))
        bridge, _, history, nia, bitrix, post_send, deleter, post_delete = items
        result = await bridge.run_once()

        self.assertEqual(result.reason, "m69_post_anchor_history_failed")
        self.assertEqual((result.history_read_count, result.exact_scope_call_count), (1, 0))
        self.assertEqual(history.calls, [900])
        for dependency in (nia, bitrix, post_send, deleter, post_delete):
            self.assertEqual(dependency.calls, [])
        self.assertNotIn("private response", result.model_dump_json())

    async def test_unprobed_m68_stops_before_history(self):
        owner = ready_owner()
        history = PostAnchorReader(inbound_payload())
        bridge = PostAnchorExactScopeBridge(
            plan=build_protected_real_roundtrip_plan(),
            preflight_adapter=owner,
            history_reader=history,
            nia_sender=Recorder(None),
            bitrix_sender=Recorder(None),
            post_send_history_reader=HistoryReader(),
            deleter=Deleter(),
            post_delete_history_reader=HistoryReader(False),
        )
        result = await bridge.run_once()
        self.assertEqual(result.reason, "m69_preflight_unavailable")
        self.assertEqual(history.calls, [])
        self.assertTrue(owner.cleared)

    async def test_reuse_performs_no_second_read_or_send(self):
        items = await bridge_for(inbound_payload())
        bridge, _, history, nia, bitrix, *_ = items
        await bridge.run_once()
        result = await bridge.run_once()

        self.assertEqual(result.reason, "m69_reuse_rejected")
        self.assertEqual(history.calls, [900])
        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(len(bitrix.calls), 1)

    def test_source_has_no_real_source_client_command_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m69_post_anchor_bridge.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "get_session_history(", "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
