import json
import unittest

import httpx

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthRecord,
    StoredOAuthAccessView,
)
from bitrix_connector.bitrix_history_r0_m86_concrete_lifecycle_operations import (
    M86ConcreteLifecycleOperations,
    M86I_HTTP_NAMES,
)
from bitrix_connector.bitrix_history_r0_m86_protected_lifecycle_resources import (
    M86ProtectedLifecycleResourceOwner,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)
from bitrix_connector.bot_v2_preflight import CONTROLLED_BOT_CODE
from bitrix_connector.config import load_settings
from bitrix_connector.models import NormalizedBitrixEvent


class CredentialBackend:
    def __init__(self):
        values = (
            "bitrix.fixture.invalid",
            "fixture-member",
            "fixture-client",
            "fixture-secret",
            "mongodb://fixture.invalid",
            "fixture-db",
            "fixture-installations",
        )
        self.buffers = {
            name: bytearray(value.encode())
            for name, value in zip(PROTECTED_SETTING_NAMES, values, strict=True)
        }
        self.record = InjectedWindowsCredentialRecord(
            target_id=M80_CREDENTIAL_TARGET_ID,
            buffers=self.buffers,
        )
        self.fetch_calls = 0
        self.close_calls = 0

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        if target_id != M80_CREDENTIAL_TARGET_ID:
            raise AssertionError("unexpected target")
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()


class OAuthBackend:
    def __init__(self):
        self.buffer = bytearray(b"fixture-m86i-token")
        self.record = InjectedStoredOAuthRecord(access_token=self.buffer)
        self.load_calls = 0
        self.close_calls = 0

    async def load_stored_once(self, _settings):
        self.load_calls += 1
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()


def revision():
    return {"result": {"rest": 35, "web": 1, "mobile": 1, "desktop": 1}}


def bots():
    return {
        "result": {
            "bots": [{
                "id": 373259,
                "code": CONTROLLED_BOT_CODE,
                "type": "openline",
                "isSupportOpenline": True,
                "eventMode": "webhook",
                "isHidden": True,
                "isReactionsEnabled": False,
            }],
            "hasNextPage": False,
        }
    }


def line_dialog():
    return {
        "result": {
            "id": 78733,
            "dialog_id": "chat78733",
            "entity_type": "LINES",
            "entity_id": "fixture|13|fixture|fixture",
        }
    }


def line_config():
    return {
        "result": {
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
    }


def history_dialog():
    return {
        "result": {
            "id": 78733,
            "dialog_id": "chat78733",
            "entity_type": "LINES",
            "entity_id": "fixture|13|fixture|fixture",
            "entity_data_1": "a|b|c|d|e|900",
            "role": "guest",
            "last_message_id": 700,
        }
    }


def message(message_id, sender_id, text):
    return {
        "id": message_id,
        "chatid": 78733,
        "senderid": sender_id,
        "recipientid": "chat78733",
        "date": "2026-08-05T00:00:00+00:00",
        "text": text,
        "params": {},
    }


def history(*, include_reply):
    messages = [message(701, 51, "fixture inbound")]
    users = [
        {"id": 51, "connector": True},
        {"id": 373259, "connector": False},
    ]
    if include_reply:
        messages.append(message(800, 373259, "fixture reply"))
    return {
        "result": {
            "chatId": 78733,
            "sessionId": 900,
            "message": messages,
            "users": users,
        }
    }


class HermeticHttpFactory:
    def __init__(self, *, rollback=False, event_mode=False):
        self.rollback = rollback
        self.event_mode = event_mode
        self.calls = []
        self.requests = []
        self.clients = []
        self.per_name = {}

    async def __call__(self, name, timeout):
        self.calls.append((name, timeout))
        self.per_name[name] = 0

        async def handler(request):
            self.per_name[name] += 1
            self.requests.append((name, request.url.path, json.loads(request.content)))
            call = self.per_name[name]
            if name == "preflight_bot":
                payload = revision() if call == 1 else bots()
            elif name == "preflight_dialog":
                payload = history_dialog() if call == 1 else line_config()
            elif name == "roundtrip_history":
                if self.event_mode:
                    payload = history(
                        include_reply=(not self.rollback and call == 1)
                    )
                else:
                    payload = (
                        history(include_reply=False)
                        if call == 1 or (self.rollback and call == 3)
                        else history(include_reply=not self.rollback)
                    )
            elif name == "nia":
                payload = {"respuesta": "fixture reply"}
            elif name == "bitrix":
                payload = {"result": {"id": 800}}
            elif name == "deleter":
                payload = {"result": {"result": True}}
            else:
                raise AssertionError("unexpected client")
            return httpx.Response(200, json=payload)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=timeout
        )
        self.clients.append(client)
        return client


class Waiter:
    def __init__(self):
        self.calls = 0

    async def __call__(self, _settings, _token_view, _outcome):
        self.calls += 1


def lifecycle(*, rollback=False, expected_sender_id=51):
    credential = CredentialBackend()
    oauth = OAuthBackend()
    http_factory = HermeticHttpFactory(rollback=rollback)
    waiter = Waiter()
    operations = M86ConcreteLifecycleOperations(
        nia_base_url="https://nia.fixture.invalid",
        http_client_factory=http_factory,
        cross_turn_waiter=waiter,
        expected_sender_id=expected_sender_id,
    )
    owner = M86ProtectedLifecycleResourceOwner(
        credential_backend=credential,
        oauth_backend=oauth,
        preflight_operation=operations.preflight,
        cross_turn_operation=operations.cross_turn,
        m88_operation=operations.m88,
        execution_enabled=True,
    )
    return owner, credential, oauth, http_factory, waiter, operations


class M86ConcreteLifecycleOperationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_path_uses_callback_token_without_refresh_or_input_history(self):
        factory = HermeticHttpFactory(event_mode=True)
        operations = M86ConcreteLifecycleOperations(
            nia_base_url="https://nia.fixture.invalid",
            http_client_factory=factory,
            cross_turn_waiter=Waiter(),
        )
        settings = load_settings(
            {
                "NIA_BITRIX_MODE": "off",
                "NIA_BITRIX_DOMAIN": "bitrix.fixture.invalid",
                "NIA_BITRIX_MEMBER_ID": "fixture-member",
            }
        )
        token = bytearray(b"event-token-fixture")
        view = StoredOAuthAccessView(token)
        outcome = await operations.preflight(settings, view)
        event = NormalizedBitrixEvent.model_validate(
            {
                "event": "ONIMBOTV2MESSAGEADD",
                "timestamp": 1772093963,
                "bot_id": 373259,
                "message_id": 700,
                "chat_id": 78733,
                "dialog_id": "chat78733",
                "author_id": 51,
                "text": "fixture inbound",
                "user_id": 51,
                "user_is_connector": True,
                "domain": "bitrix.fixture.invalid",
                "member_id": "fixture-member",
            }
        )
        result = await operations.m88_event(settings, view, outcome, event)
        view.close()
        token[:] = b"\x00" * len(token)

        self.assertEqual(result.state, "VERIFIED")
        self.assertEqual(result.history_read_calls, 1)
        self.assertEqual(result.nia_call_count, 1)
        self.assertEqual(result.bitrix_send_call_count, 1)
        self.assertEqual(result.delete_call_count, 0)
        self.assertEqual(
            tuple(name for name, _ in factory.calls),
            M86I_HTTP_NAMES,
        )
        self.assertTrue(all(client.is_closed for client in factory.clients))
        self.assertFalse(any(token))

    async def test_verified_path_reuses_one_oauth_and_closes_all_resources(self):
        owner, credential, oauth, factory, waiter, operations = lifecycle()

        snapshot = await owner.run_once(execute=True)

        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertEqual((snapshot.oauth_load_calls, snapshot.oauth_refresh_calls), (1, 0))
        self.assertEqual(snapshot.oauth_token_view_reads, 2)
        self.assertEqual(tuple(name for name, _ in factory.calls), M86I_HTTP_NAMES)
        self.assertEqual(len(factory.requests), 8)
        self.assertEqual(
            sum(path == "/rest/imopenlines.dialog.get" for _, path, _ in factory.requests),
            1,
        )
        self.assertEqual(waiter.calls, 1)
        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
        self.assertTrue(snapshot.private_resources_closed)
        self.assertTrue(all(client.is_closed for client in factory.clients))
        self.assertTrue(all(not any(value) for value in credential.buffers.values()))
        self.assertFalse(any(oauth.buffer))
        self.assertEqual(repr(operations), "M86ConcreteLifecycleOperations(<redacted>)")

    async def test_failed_post_send_verification_deletes_only_receipt_and_rechecks(self):
        owner, _, oauth, factory, _, _ = lifecycle(rollback=True)

        snapshot = await owner.run_once(execute=True)

        self.assertEqual(snapshot.state, "ROLLED-BACK")
        self.assertEqual(len(factory.requests), 10)
        deletes = [item for item in factory.requests if item[0] == "deleter"]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0][2]["messageId"], 800)
        self.assertEqual(factory.per_name["roundtrip_history"], 3)
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
        self.assertTrue(all(client.is_closed for client in factory.clients))

    async def test_sender_id_can_be_deferred_to_exact_unique_chat_candidate(self):
        owner, _, _, factory, _, _ = lifecycle(expected_sender_id=None)

        snapshot = await owner.run_once(execute=True)

        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertEqual(len(factory.requests), 8)

    async def test_preview_opens_nothing(self):
        owner, credential, oauth, factory, waiter, _ = lifecycle()

        snapshot = await owner.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual((credential.fetch_calls, oauth.load_calls), (0, 0))
        self.assertEqual((factory.calls, waiter.calls), ([], 0))


if __name__ == "__main__":
    unittest.main()
