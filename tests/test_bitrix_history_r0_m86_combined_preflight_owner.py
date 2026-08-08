import asyncio
import json
import unittest
from pathlib import Path

import httpx

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_MAGIC,
    WindowsCredentialManagerBackend,
)
from bitrix_connector.bitrix_history_r0_m86_combined_preflight_owner import (
    M86CombinedPreflightOwner,
    M86C_HTTP_NAMES,
    build_real_m86_combined_preflight_owner,
)
from bitrix_connector.bitrix_history_r0_m86_stored_oauth_backend import (
    M86StoredOAuthBackend,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)
from bitrix_connector.bot_v2_preflight import CONTROLLED_BOT_CODE


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-m86-c-stored-token"


def protected_blob():
    values = (
        "bitrix.fixture.invalid",
        "fixture-member",
        "fixture-client",
        "fixture-client-secret",
        "mongodb://fixture.invalid",
        "fixture-db",
        "fixture-installations",
    )
    blob = bytearray(M84_BLOB_MAGIC)
    for name, text in zip(PROTECTED_SETTING_NAMES, values, strict=True):
        encoded_name = name.encode("ascii")
        encoded_value = text.encode("utf-8")
        blob.extend(len(encoded_name).to_bytes(2, "big"))
        blob.extend(encoded_name)
        blob.extend(len(encoded_value).to_bytes(4, "big"))
        blob.extend(encoded_value)
    return blob


class CredentialNativeFixture:
    def __init__(self):
        self.blob = protected_blob()
        self.read_calls = 0
        self.close_calls = 0

    async def read_generic_blob_once(self, target_id):
        self.read_calls += 1
        if target_id != M80_CREDENTIAL_TARGET_ID:
            raise AssertionError("unexpected credential target")
        blob, self.blob = self.blob, bytearray()
        return blob

    async def close(self):
        self.close_calls += 1
        self.blob[:] = b"\x00" * len(self.blob)


class OAuthProviderFixture:
    def __init__(self):
        self.get_calls = []
        self.refresh_calls = 0

    async def get_access_token(self, member_id):
        self.get_calls.append(member_id)
        return TOKEN

    async def refresh_access_token(self, *_args):
        self.refresh_calls += 1
        raise AssertionError("refresh must never run")


class OAuthResourcesFixture:
    def __init__(self):
        self.oauth_provider = OAuthProviderFixture()
        self.member_id = "fixture-member"
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class OAuthFactoryFixture:
    def __init__(self):
        self.resources = OAuthResourcesFixture()
        self.calls = []

    async def build(self, settings, *, timeout_seconds):
        self.calls.append((settings, timeout_seconds))
        return self.resources


class FailingOAuthFactoryFixture:
    def __init__(self):
        self.calls = 0

    async def build(self, settings, *, timeout_seconds):
        self.calls += 1
        raise RuntimeError("fixture oauth unavailable")


def bot_revision():
    return {
        "result": {"rest": 35, "web": 1, "mobile": 1, "desktop": 1}
    }


def bot_list(*, bot_id=373259):
    return {
        "result": {
            "bots": [
                {
                    "id": bot_id,
                    "code": CONTROLLED_BOT_CODE,
                    "type": "openline",
                    "isSupportOpenline": True,
                    "eventMode": "webhook",
                    "isHidden": True,
                    "isReactionsEnabled": False,
                }
            ],
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


class HermeticPreflightHttpFactory:
    def __init__(
        self,
        *,
        bot_id=373259,
        revision_payload=None,
        revision_status=200,
        revision_transport_error=False,
        list_payload=None,
        cancel_name=None,
        close_fail_name=None,
    ):
        self.bot_id = bot_id
        self.revision_payload = revision_payload
        self.revision_status = revision_status
        self.revision_transport_error = revision_transport_error
        self.list_payload = list_payload
        self.cancel_name = cancel_name
        self.close_fail_name = close_fail_name
        self.calls = []
        self.requests = []
        self.clients = []

    async def __call__(self, name, timeout_seconds):
        self.calls.append((name, timeout_seconds))
        if name == self.cancel_name:
            raise asyncio.CancelledError()
        counter = 0

        async def handler(request):
            nonlocal counter
            counter += 1
            self.requests.append((name, request.url.path, json.loads(request.content)))
            if name == "preflight_bot":
                if counter == 1 and self.revision_transport_error:
                    raise httpx.ConnectError("fixture transport", request=request)
                payload = (
                    self.revision_payload or bot_revision()
                    if counter == 1
                    else self.list_payload or bot_list(bot_id=self.bot_id)
                )
            elif name == "preflight_dialog":
                payload = history_dialog() if counter == 1 else line_config()
            else:
                raise AssertionError("unexpected preflight HTTP name")
            status = self.revision_status if name == "preflight_bot" and counter == 1 else 200
            return httpx.Response(status, json=payload)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout_seconds,
        )
        if name == self.close_fail_name:
            original_close = client.aclose

            async def failed_close():
                await original_close()
                raise RuntimeError("private close failure")

            client.aclose = failed_close
        self.clients.append(client)
        return client


def owner(*, http_factory=None):
    native = CredentialNativeFixture()
    credential = WindowsCredentialManagerBackend(native=native)
    oauth_factory = OAuthFactoryFixture()
    oauth = M86StoredOAuthBackend(resources_factory=oauth_factory)
    http_factory = http_factory or HermeticPreflightHttpFactory()
    value = M86CombinedPreflightOwner(
        credential_backend=credential,
        oauth_backend=oauth,
        http_client_factory=http_factory,
        hermetic_execution=True,
    )
    return value, native, oauth, oauth_factory, http_factory


class M86CombinedPreflightOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_m84_m86a_m86b_run_exact_combined_preflight_and_retain_anchor(self):
        value, native, oauth, oauth_factory, http_factory = owner()

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertEqual(snapshot.failure_stage, "none")
        self.assertEqual(snapshot.credential_source_read_calls, 7)
        self.assertEqual((snapshot.oauth_load_calls, snapshot.oauth_refresh_calls), (1, 0))
        self.assertEqual(snapshot.oauth_token_view_reads, 1)
        self.assertEqual(snapshot.http_client_factory_calls, 2)
        self.assertEqual(
            (snapshot.bot_read_calls, snapshot.openline_read_calls),
            (2, 1),
        )
        self.assertEqual((snapshot.history_dialog_read_calls, snapshot.history_read_calls), (1, 0))
        self.assertEqual(snapshot.resource_close_calls, 2)
        self.assertTrue(snapshot.combined_preflight_verified)
        self.assertTrue(snapshot.history_anchor_available)
        self.assertTrue(snapshot.private_resources_closed)
        self.assertEqual((snapshot.messages_sent, snapshot.deletions_executed), (0, 0))
        self.assertEqual(tuple(name for name, _ in http_factory.calls), M86C_HTTP_NAMES)
        self.assertEqual(len(http_factory.requests), 4)
        self.assertEqual(
            sum(
                path == "/rest/imopenlines.dialog.get"
                for _, path, _ in http_factory.requests
            ),
            1,
        )
        self.assertFalse(any("send" in path.lower() or "delete" in path.lower() for _, path, _ in http_factory.requests))
        self.assertTrue(all(client.is_closed for client in http_factory.clients))
        self.assertEqual((native.read_calls, native.close_calls), (1, 1))
        self.assertEqual((oauth.load_calls, oauth.token_read_calls, oauth.close_calls), (1, 1, 1))
        self.assertEqual(len(oauth_factory.calls), 1)
        self.assertEqual(oauth_factory.resources.oauth_provider.get_calls, ["fixture-member"])
        self.assertEqual(oauth_factory.resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(oauth_factory.resources.close_calls, 1)

        outcome = value.take_history_outcome_once()
        anchor = outcome.require_anchor()
        self.assertEqual((anchor.session_id, anchor.baseline_last_message_id), (900, 700))
        with self.assertRaisesRegex(RuntimeError, "outcome_unavailable"):
            value.take_history_outcome_once()

    async def test_bot_drift_stops_before_openline_and_history(self):
        http_factory = HermeticPreflightHttpFactory(bot_id=999999)
        value, native, oauth, oauth_factory, _ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_stage, "bot_contract_stage")
        self.assertEqual(tuple(name for name, _ in http_factory.calls), ("preflight_bot",))
        self.assertEqual(len(http_factory.requests), 2)
        self.assertEqual(snapshot.resource_close_calls, 1)
        self.assertTrue(snapshot.private_resources_closed)
        self.assertEqual((native.close_calls, oauth.close_calls), (1, 1))
        self.assertEqual(oauth_factory.resources.oauth_provider.refresh_calls, 0)
        with self.assertRaisesRegex(RuntimeError, "outcome_unavailable"):
            value.take_history_outcome_once()

    async def test_invalid_revision_is_categorized_before_bot_list(self):
        http_factory = HermeticPreflightHttpFactory(
            revision_payload={"result": {"rest": "invalid"}},
        )
        value, *_ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(
            (snapshot.state, snapshot.failure_stage),
            ("NO-GO", "bot_revision_contract_stage"),
        )
        self.assertEqual(len(http_factory.requests), 1)

    async def test_revision_transport_failure_is_categorized_safely(self):
        http_factory = HermeticPreflightHttpFactory(
            revision_transport_error=True,
        )
        value, *_ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(
            (snapshot.state, snapshot.failure_stage),
            ("NO-GO", "bot_revision_transport_stage"),
        )
        self.assertEqual(len(http_factory.requests), 1)

    async def test_revision_permanent_failure_is_categorized_safely(self):
        http_factory = HermeticPreflightHttpFactory(
            revision_payload={"error": "NO_AUTH_FOUND"},
            revision_status=401,
        )
        value, *_ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(
            (snapshot.state, snapshot.failure_stage),
            ("NO-GO", "bot_revision_permanent_stage"),
        )
        self.assertEqual(len(http_factory.requests), 1)

    async def test_revision_expired_token_is_categorized_without_refresh(self):
        http_factory = HermeticPreflightHttpFactory(
            revision_payload={"error": "expired_token"},
            revision_status=401,
        )
        value, _, _, oauth_factory, _ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(
            (snapshot.state, snapshot.failure_stage),
            ("NO-GO", "bot_revision_token_expired_stage"),
        )
        self.assertEqual(oauth_factory.resources.oauth_provider.refresh_calls, 0)

    async def test_revision_retryable_failure_is_categorized_safely(self):
        http_factory = HermeticPreflightHttpFactory(
            revision_payload={"error": "INTERNAL_SERVER_ERROR"},
            revision_status=500,
        )
        value, *_ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(
            (snapshot.state, snapshot.failure_stage),
            ("NO-GO", "bot_revision_retryable_stage"),
        )
        self.assertEqual(len(http_factory.requests), 1)

    async def test_invalid_bot_list_is_categorized_after_revision(self):
        http_factory = HermeticPreflightHttpFactory(
            list_payload={"result": {"bots": "invalid"}},
        )
        value, *_ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(
            (snapshot.state, snapshot.failure_stage),
            ("NO-GO", "bot_list_stage"),
        )
        self.assertEqual(len(http_factory.requests), 2)

    async def test_oauth_failure_is_categorized_before_http(self):
        native = CredentialNativeFixture()
        credential = WindowsCredentialManagerBackend(native=native)
        oauth_factory = FailingOAuthFactoryFixture()
        oauth = M86StoredOAuthBackend(resources_factory=oauth_factory)
        http_factory = HermeticPreflightHttpFactory()
        value = M86CombinedPreflightOwner(
            credential_backend=credential,
            oauth_backend=oauth,
            http_client_factory=http_factory,
            hermetic_execution=True,
        )

        snapshot = await value.run_once()

        self.assertEqual((snapshot.state, snapshot.failure_stage), ("NO-GO", "oauth_stage"))
        self.assertEqual(snapshot.http_client_factory_calls, 0)
        self.assertTrue(snapshot.private_resources_closed)
        self.assertEqual(oauth_factory.calls, 1)

    async def test_cancellation_during_second_http_factory_is_terminal_and_closed(self):
        http_factory = HermeticPreflightHttpFactory(cancel_name="preflight_dialog")
        value, native, oauth, _, _ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertEqual(snapshot.failure_stage, "dialog_stage")
        self.assertEqual(tuple(name for name, _ in http_factory.calls), ("preflight_bot", "preflight_dialog"))
        self.assertEqual(snapshot.resource_close_calls, 1)
        self.assertTrue(snapshot.private_resources_closed)
        self.assertEqual((native.close_calls, oauth.close_calls), (1, 1))
        self.assertTrue(http_factory.clients[0].is_closed)

    async def test_close_failure_is_visible_and_stops_combined_preflight(self):
        http_factory = HermeticPreflightHttpFactory(close_fail_name="preflight_bot")
        value, native, oauth, _, _ = owner(http_factory=http_factory)

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_stage, "cleanup_stage")
        self.assertEqual(snapshot.resource_close_calls, 1)
        self.assertFalse(snapshot.private_resources_closed)
        self.assertEqual((native.close_calls, oauth.close_calls), (1, 1))
        self.assertTrue(http_factory.clients[0].is_closed)

    async def test_reuse_is_rejected_without_second_source_oauth_or_http(self):
        value, native, oauth, _, http_factory = owner()

        first = await value.run_once()
        value.take_history_outcome_once()
        second = await value.run_once()

        self.assertEqual(first.state, "VERIFIED")
        self.assertEqual(second.reason, "m86c_owner_reuse_rejected")
        self.assertEqual(second.failure_stage, "not_run")
        self.assertEqual((native.read_calls, oauth.load_calls), (1, 1))
        self.assertEqual(len(http_factory.calls), 2)

    async def test_real_binding_is_inert_and_opens_no_source_oauth_or_http(self):
        value = build_real_m86_combined_preflight_owner()
        credential = value._credential_backend
        oauth = value._oauth_backend

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(snapshot.failure_stage, "not_run")
        self.assertEqual(snapshot.owner_calls, 0)
        self.assertFalse(snapshot.hermetic_execution)
        self.assertEqual(snapshot.http_client_factory_calls, 0)
        self.assertEqual(snapshot.remaining_real_bindings, 2)
        self.assertFalse(snapshot.first_confirmation_request_ready)
        self.assertFalse(snapshot.attention_required_now)
        self.assertIsNone(credential._native._api)
        self.assertEqual((oauth.load_calls, oauth.token_read_calls, oauth.close_calls), (0, 0, 0))
        self.assertIsNone(oauth._resources)

    def test_repr_and_source_expose_no_secret_command_message_or_test_transport(self):
        value, *_ = owner()
        self.assertEqual(repr(value), "M86CombinedPreflightOwner(<redacted>)")
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_combined_preflight_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "mocktransport",
            ".env",
            "dotenv",
            "os.environ",
            "pymongo",
            "motor",
            "refresh_access_token(",
            "send_approved",
            "delete_approved",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
