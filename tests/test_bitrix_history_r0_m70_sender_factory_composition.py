import unittest
from copy import deepcopy
from pathlib import Path

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_history_r0_m68_combined_preflight import (
    CombinedR1PreflightAdapter,
    InjectedClosedProbeResult,
)
from bitrix_connector.bitrix_history_r0_m70_sender_factory_composition import (
    InjectedFixtureSenderResource,
    SenderFactoryCompositionStatus,
    SenderFactoryM69Composition,
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


async def ready_owner(*, probed=True, bot_id=373259):
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
                existing_bot_id=bot_id,
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
    if probed:
        await owner.probe_once()
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


class PostAnchorReader:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def read_post_anchor_history(self, *, session_id):
        self.calls.append(session_id)
        return self.payload


class Sender:
    def __init__(self, *, nia_result=None, bitrix_result=None, fail=False):
        self.nia_result = nia_result
        self.bitrix_result = bitrix_result
        self.fail = fail
        self.calls = []

    async def send_approved_text(self, payload):
        self.calls.append(payload)
        if self.fail:
            raise RuntimeError("private nia failure")
        return self.nia_result

    async def send_approved_message(self, payload):
        self.calls.append(payload)
        if self.fail:
            raise RuntimeError("private bitrix failure")
        return self.bitrix_result


class Factory:
    def __init__(self, sender, *, fail=False, close_fail=False):
        self.sender = sender
        self.fail = fail
        self.close_fail = close_fail
        self.calls = 0
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_fail:
            raise RuntimeError("private close failure")

    async def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private factory failure")
        return InjectedFixtureSenderResource(
            sender=self.sender,
            close_callback=self.close,
        )


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


def default_factories():
    nia = Factory(
        Sender(
            nia_result=NiaClientResult.succeeded(
                NiaChatResponse(respuesta="respuesta fixture"), http_status=200
            )
        )
    )
    bitrix = Factory(
        Sender(
            bitrix_result=BitrixClientResult.succeeded(
                BitrixSendResponse.model_validate({"result": {"id": 800}}),
                http_status=200,
            )
        )
    )
    return nia, bitrix


async def composition(payload, *, nia_factory=None, bitrix_factory=None):
    nia_default, bitrix_default = default_factories()
    nia_factory = nia_factory or nia_default
    bitrix_factory = bitrix_factory or bitrix_default
    history = PostAnchorReader(payload)
    post_send = HistoryReader()
    deleter = Deleter()
    post_delete = HistoryReader(False)
    owner = SenderFactoryM69Composition(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=await ready_owner(),
        history_reader=history,
        nia_sender_factory=nia_factory,
        bitrix_sender_factory=bitrix_factory,
        post_send_history_reader=post_send,
        deleter=deleter,
        post_delete_history_reader=post_delete,
        expected_sender_id=51,
    )
    return owner, history, nia_factory, bitrix_factory, post_send, deleter, post_delete


class SenderFactoryM69CompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_builds_calls_and_closes_each_fixture_sender_once(self):
        items = await composition(inbound_payload())
        owner, history, nia, bitrix, post_send, deleter, post_delete = items

        result = await owner.run_once()

        self.assertEqual(result.status, SenderFactoryCompositionStatus.VERIFIED)
        self.assertEqual(result.reason, "m70_senders_verified_with_m69")
        self.assertEqual(history.calls, [900])
        self.assertEqual((nia.calls, len(nia.sender.calls), nia.close_calls), (1, 1, 1))
        self.assertEqual(
            (bitrix.calls, len(bitrix.sender.calls), bitrix.close_calls), (1, 1, 1)
        )
        self.assertEqual(post_send.calls, [900])
        self.assertEqual(deleter.calls, [])
        self.assertEqual(post_delete.calls, [])
        self.assertTrue(owner.cleared)

    async def test_invalid_history_does_not_construct_senders(self):
        payload = deepcopy(inbound_payload())
        payload["result"]["chatId"] = 99999
        items = await composition(payload)
        owner, history, nia, bitrix, *_ = items

        result = await owner.run_once()

        self.assertEqual(result.reason, "m70_m69_no_go")
        self.assertEqual(history.calls, [900])
        self.assertEqual((nia.calls, bitrix.calls), (0, 0))
        self.assertEqual((result.nia_factory_calls, result.bitrix_factory_calls), (0, 0))

    async def test_nia_factory_or_sender_failure_closes_and_stops_bitrix(self):
        cases = (
            Factory(Sender(), fail=True),
            Factory(Sender(fail=True)),
            Factory(
                Sender(
                    nia_result=NiaClientResult.succeeded(
                        NiaChatResponse(respuesta="fixture"), http_status=200
                    )
                ),
                close_fail=True,
            ),
        )
        for nia in cases:
            with self.subTest(factory_fail=nia.fail, close_fail=nia.close_fail):
                bitrix = default_factories()[1]
                owner, _, _, _, post_send, deleter, post_delete = await composition(
                    inbound_payload(), nia_factory=nia, bitrix_factory=bitrix
                )
                result = await owner.run_once()
                self.assertEqual(result.reason, "m70_m69_no_go")
                self.assertEqual(bitrix.calls, 0)
                self.assertEqual(post_send.calls, [])
                self.assertEqual(deleter.calls, [])
                self.assertEqual(post_delete.calls, [])
                expected_close = 0 if nia.fail else 1
                self.assertEqual(nia.close_calls, expected_close)

    async def test_bitrix_factory_failure_occurs_after_closed_nia(self):
        nia = default_factories()[0]
        bitrix = Factory(Sender(), fail=True)
        owner, _, _, _, post_send, deleter, post_delete = await composition(
            inbound_payload(), nia_factory=nia, bitrix_factory=bitrix
        )

        result = await owner.run_once()

        self.assertEqual(result.reason, "m70_m69_no_go")
        self.assertEqual((nia.calls, len(nia.sender.calls), nia.close_calls), (1, 1, 1))
        self.assertEqual((bitrix.calls, bitrix.close_calls), (1, 0))
        self.assertEqual(post_send.calls, [])
        self.assertEqual(deleter.calls, [])
        self.assertEqual(post_delete.calls, [])

    async def test_reuse_does_not_rebuild_or_resend(self):
        owner, history, nia, bitrix, *_ = await composition(inbound_payload())
        await owner.run_once()
        result = await owner.run_once()

        self.assertEqual(result.reason, "m70_reuse_rejected")
        self.assertEqual(history.calls, [900])
        self.assertEqual((nia.calls, bitrix.calls), (1, 1))
        self.assertEqual((nia.close_calls, bitrix.close_calls), (1, 1))

    def test_resource_rejects_non_fixture_metadata(self):
        async def close():
            return None

        with self.assertRaises(ValueError):
            InjectedFixtureSenderResource(
                sender=Sender(), close_callback=close, external_calls=1
            )
        with self.assertRaises(ValueError):
            InjectedFixtureSenderResource(
                sender=Sender(), close_callback=close, real_client_constructed=True
            )

    def test_source_has_no_real_clients_sources_commands_or_services(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m70_sender_factory_composition.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "pilotdiscoveryoauthfactory", "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
