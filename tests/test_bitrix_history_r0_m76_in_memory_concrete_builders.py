import json
import unittest
from pathlib import Path

import httpx

from bitrix_connector.bitrix_client import BitrixClient, BitrixClientDecision
from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryR0Client,
    BitrixHistoryReadDecision,
)
from bitrix_connector.bitrix_history_r0_m70_sender_factory_composition import (
    InjectedFixtureSenderResource,
)
from bitrix_connector.bitrix_history_r0_m76_in_memory_concrete_builders import (
    BITRIX_REPLY_DELETE_PATH,
    ConcreteBindingStatus,
    ExactReplyDeleteClient,
    InMemoryConcreteBindingBuilders,
    InMemoryConcreteBindingSettings,
    InjectedInMemoryHttpResource,
)
from bitrix_connector.bitrix_history_r0_reply_rollback_contract import (
    build_reply_rollback_delete_preview,
)
from bitrix_connector.nia_client import NiaClient, NiaClientDecision
from bitrix_connector.output_review import (
    BitrixMessageFieldsPreview,
    BitrixMessagePayloadPreview,
)
from bitrix_connector.preflight import NiaTextPayloadPreview


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-private-token-m76"


class MemoryHttpFactory:
    def __init__(self, *, invalid_delete=False):
        self.invalid_delete = invalid_delete
        self.calls = []
        self.requests = []
        self.clients = []

    async def handler(self, request):
        self.requests.append(request)
        path = request.url.path
        if path == "/nia/chat":
            return httpx.Response(200, json={"respuesta": "respuesta fixture"})
        if path == "/rest/imbot.v2.Chat.Message.send":
            return httpx.Response(200, json={"result": {"id": 800}})
        if path == BITRIX_REPLY_DELETE_PATH:
            if self.invalid_delete:
                return httpx.Response(200, json={"result": True})
            return httpx.Response(200, json={"result": {"result": True}})
        if path == "/rest/imopenlines.session.history.get":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "chatId": 78733,
                        "sessionId": 900,
                        "message": [
                            {
                                "id": 701,
                                "chatid": 78733,
                                "senderid": 51,
                                "recipientid": "chat78733",
                                "date": "2026-08-04T00:00:00+00:00",
                                "text": "fixture inbound",
                            }
                        ],
                        "users": [{"id": 51, "connector": True}],
                    }
                },
            )
        return httpx.Response(404, json={"error": "fixture_not_found"})

    def __call__(self, name, timeout):
        self.calls.append((name, timeout))
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler),
            timeout=timeout,
        )
        self.clients.append(client)
        return InjectedInMemoryHttpResource(client=client)


def builders(factory=None):
    factory = factory or MemoryHttpFactory()
    value = InMemoryConcreteBindingBuilders(
        settings=InMemoryConcreteBindingSettings(
            nia_base_url="https://nia.fixture.local",
            portal_url="https://bitrix.fixture.local",
            timeout_seconds=10,
        ),
        http_resource_factory=factory,
    )
    return value, factory


class M76InMemoryConcreteBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_constructor_is_dormant_until_each_explicit_builder_call(self):
        owner, factory = builders()

        self.assertEqual(factory.calls, [])
        snapshot = await owner.close()

        self.assertEqual(snapshot.status, ConcreteBindingStatus.NO_GO)
        self.assertEqual(snapshot.http_resource_factory_calls, 0)
        self.assertFalse(snapshot.concrete_clients_constructed_in_memory)

    async def test_four_concrete_clients_execute_only_over_mock_transport(self):
        owner, factory = builders()
        nia = await owner.build_nia(10)
        bitrix = await owner.build_bitrix(TOKEN, 10)
        deleter = await owner.build_deleter(TOKEN, 10)
        history = await owner.build_history(TOKEN, 10)

        nia_result = await nia.dependency.send_approved_text(
            NiaTextPayloadPreview(session_id="fixture-session", mensaje="fixture")
        )
        bitrix_result = await bitrix.dependency.send_approved_message(
            BitrixMessagePayloadPreview(
                botId=373259,
                dialogId="chat78733",
                fields=BitrixMessageFieldsPreview(message="fixture reply"),
            )
        )
        delete_result = await deleter.dependency.delete_approved_reply(
            build_reply_rollback_delete_preview(bot_id=373259, sent_message_id=800)
        )
        history_result = await history.dependency.get_session_history(900)
        snapshot = await owner.close()

        self.assertIsInstance(nia.dependency, NiaClient)
        self.assertIsInstance(bitrix.dependency, BitrixClient)
        self.assertIsInstance(deleter.dependency, ExactReplyDeleteClient)
        self.assertIsInstance(history.dependency, BitrixHistoryR0Client)
        self.assertEqual(nia_result.decision, NiaClientDecision.SUCCESS)
        self.assertEqual(bitrix_result.decision, BitrixClientDecision.SUCCESS)
        self.assertEqual(delete_result, {"result": {"result": True}})
        self.assertEqual(history_result.decision, BitrixHistoryReadDecision.SUCCESS)
        self.assertEqual(snapshot.status, ConcreteBindingStatus.VERIFIED)
        self.assertEqual(snapshot.close_calls, 4)
        self.assertEqual(len(factory.calls), 4)
        self.assertTrue(all(client.is_closed for client in factory.clients))
        self.assertNotIn(TOKEN, repr(owner))
        self.assertNotIn(TOKEN, snapshot.model_dump_json())

    async def test_bitrix_clients_use_preloaded_token_without_provider_or_refresh(self):
        owner, _ = builders()
        bitrix = await owner.build_bitrix(TOKEN, 10)

        self.assertIsNone(bitrix.dependency._token_provider)
        self.assertEqual(bitrix.dependency._access_token, TOKEN)
        await bitrix.close()
        snapshot = await owner.close()

        self.assertFalse(snapshot.oauth_refresh_surface_used)
        self.assertTrue(snapshot.oauth_preloaded_token_only)

    async def test_exact_delete_uses_only_approved_endpoint_and_payload_once(self):
        owner, factory = builders()
        resource = await owner.build_deleter(TOKEN, 10)
        preview = build_reply_rollback_delete_preview(
            bot_id=373259, sent_message_id=800
        )

        result = await resource.dependency.delete_approved_reply(preview)
        with self.assertRaisesRegex(RuntimeError, "reuse_or_input_invalid"):
            await resource.dependency.delete_approved_reply(preview)
        await owner.close()

        self.assertEqual(result, {"result": {"result": True}})
        self.assertEqual(len(factory.requests), 1)
        request = factory.requests[0]
        self.assertEqual(request.url.path, BITRIX_REPLY_DELETE_PATH)
        payload = json.loads(request.content)
        self.assertEqual(
            set(payload), {"botId", "messageId", "complete", "auth"}
        )
        self.assertNotIn("method", payload)

    async def test_invalid_delete_receipt_fails_closed_without_retry(self):
        factory = MemoryHttpFactory(invalid_delete=True)
        owner, _ = builders(factory)
        resource = await owner.build_deleter(TOKEN, 10)

        result = await resource.dependency.delete_approved_reply(
            build_reply_rollback_delete_preview(bot_id=373259, sent_message_id=800)
        )
        await owner.close()

        self.assertEqual(result, {})
        self.assertEqual(len(factory.requests), 1)

    async def test_each_concrete_builder_is_one_shot(self):
        owner, factory = builders()
        resource = await owner.build_nia(10)

        with self.assertRaisesRegex(RuntimeError, "builder_rejected"):
            await owner.build_nia(10)
        snapshot = await owner.close()

        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(snapshot.nia_builder_calls, 1)
        self.assertEqual(snapshot.retry_budget, 0)
        self.assertTrue(resource.transport_in_memory_only)

    async def test_timeout_drift_stops_before_http_resource_construction(self):
        owner, factory = builders()

        with self.assertRaisesRegex(RuntimeError, "builder_rejected"):
            await owner.build_history(TOKEN, 9)
        snapshot = await owner.close()

        self.assertEqual(factory.calls, [])
        self.assertEqual(snapshot.status, ConcreteBindingStatus.NO_GO)

    async def test_concrete_resource_cannot_masquerade_as_m70_fixture(self):
        owner, _ = builders()
        resource = await owner.build_nia(10)

        with self.assertRaises(ValueError):
            InjectedFixtureSenderResource(
                sender=resource.dependency,
                close_callback=resource.close,
                real_client_constructed=True,
            )
        snapshot = await owner.close()

        self.assertFalse(snapshot.m75_connected)
        self.assertFalse(snapshot.m73_connected)
        self.assertFalse(snapshot.first_confirmation_request_ready)

    def test_settings_and_http_resource_reject_unsafe_contracts(self):
        with self.assertRaises(ValueError):
            InMemoryConcreteBindingSettings(
                nia_base_url="", portal_url="https://fixture.local", timeout_seconds=10
            )
        with self.assertRaises(ValueError):
            InMemoryConcreteBindingSettings(
                nia_base_url="https://fixture.local",
                portal_url="https://fixture.local",
                timeout_seconds=10.1,
            )

    def test_source_has_no_settings_source_oauth_refresh_command_or_default_network(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m76_in_memory_concrete_builders.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "pymongo", "argparse", "input(", "subprocess", "socket",
            "pilotdiscoveryoauthfactory(", "get_access_token(",
            "refresh_access_token(", "waiting-message", "asyncclient(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
