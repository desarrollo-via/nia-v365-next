import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx

from bitrix_connector.config import load_settings
from bitrix_connector.openline_link_composition import (
    OpenLineLinkHttpResources,
    rehearse_controlled_link_with_injected_oauth,
)
from bitrix_connector.openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    LinkRehearsalStatus,
)
from bitrix_connector.openline_r0_receipt import ControlledR0Receipt
from bitrix_connector.openline_pilot_preflight import (
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    build_controlled_pilot_preview,
)
from bitrix_connector.openline_update_adapter import (
    BITRIX_OPENLINE_CONFIG_UPDATE_PATH,
    BitrixOpenLineUpdateClient,
)
from bitrix_connector.openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_GET_PATH,
    BitrixOpenLinePreflightClient,
)


NOW = datetime(2026, 7, 27, 18, 0, tzinfo=timezone.utc)
MEMBER_ID = "member-controlled"


def config_payload(bot_id=245339):
    return {
        "ID": 13,
        "LINE_NAME": "WhatApp Wazzup OFICIAL",
        "ACTIVE": "Y",
        "WELCOME_BOT_ENABLE": "Y",
        "WELCOME_BOT_JOIN": "always",
        "WELCOME_BOT_ID": bot_id,
        "WELCOME_BOT_TIME": 0,
        "WELCOME_BOT_LEFT": "close",
        "NO_ANSWER_BOT_ID": 0,
        "CLOSE_BOT_ID": 0,
        "AUTO_CLOSE_BOT_ID": 0,
        "WORKTIME_DAYOFF_BOT_ID": 0,
    }


def preview():
    preflight = OpenLinePreflightResult(
        status=OpenLinePreflightStatus.READY,
        reason="openline_snapshot_ready",
        chat_id=78733,
        dialog_id="chat78733",
        config=OpenLineConfigSnapshot.model_validate(config_payload()),
    )
    return build_controlled_pilot_preview(
        preflight=preflight,
        bot_id=CONTROLLED_BOT_ID,
        member_id=MEMBER_ID,
        webhook_url="https://nia.example.com/bitrix-connector/webhook",
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=9),
    )


def receipt():
    return ControlledR0Receipt(
        event_key="a" * 64,
        member_id=MEMBER_ID,
        bot_id=CONTROLLED_BOT_ID,
        chat_id=78733,
        dialog_id="chat78733",
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        identity_verified=True,
        persisted=False,
        nia_called=False,
        bitrix_written=False,
    )


class OAuthResources:
    def __init__(self, *, token="oauth-secret"):
        self.member_id = MEMBER_ID
        self.portal_url = "https://portal.bitrix24.test"
        self.oauth_provider = AsyncMock()
        self.oauth_provider.get_access_token.return_value = token
        self.closed = False

    async def close(self):
        self.closed = True


class ComposedLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_one_shot_adapters_restore_and_close_everything(self):
        current_bot = 245339
        calls = []

        async def handler(request):
            nonlocal current_bot
            payload = json.loads(request.content)
            calls.append((request.url.path, payload))
            if request.url.path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH:
                current_bot = payload["PARAMS"]["WELCOME_BOT_ID"]
                return httpx.Response(200, json={"result": True})
            self.assertEqual(request.url.path, BITRIX_OPENLINE_CONFIG_GET_PATH)
            return httpx.Response(200, json={"result": config_payload(current_bot)})

        shared_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(shared_http.aclose)
        built = []

        def factory(*, portal_url, access_token, timeout_seconds):
            resource = OpenLineLinkHttpResources(
                link_update_client=BitrixOpenLineUpdateClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=shared_http,
                ),
                link_read_client=BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=shared_http,
                ),
                rollback_update_client=BitrixOpenLineUpdateClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=shared_http,
                ),
                rollback_read_client=BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=shared_http,
                ),
            )
            built.append(resource)
            return resource

        oauth = OAuthResources()
        result = await rehearse_controlled_link_with_injected_oauth(
            preview=preview(),
            settings=load_settings({"NIA_BITRIX_MODE": "active"}),
            oauth_resources=oauth,
            receipt_waiter=AsyncMock(return_value=receipt()),
            receipt_timeout_seconds=1,
            timeout_seconds=3,
            http_resources_factory=factory,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.RESTORED)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(current_bot, 245339)
        self.assertEqual(
            [payload["PARAMS"]["WELCOME_BOT_ID"] for path, payload in calls if path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH],
            [CONTROLLED_BOT_ID, 245339],
        )
        self.assertEqual(sum(path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH for path, _ in calls), 2)
        oauth.oauth_provider.get_access_token.assert_awaited_once_with(MEMBER_ID)
        self.assertTrue(oauth.closed)
        self.assertTrue(built[0].closed)
        self.assertNotIn("oauth-secret", repr(result))

    async def test_token_failure_is_blocked_and_oauth_is_closed(self):
        oauth = OAuthResources()
        oauth.oauth_provider.get_access_token.side_effect = RuntimeError("secret detail")
        factory = unittest.mock.Mock()

        result = await rehearse_controlled_link_with_injected_oauth(
            preview=preview(),
            settings=load_settings({}),
            oauth_resources=oauth,
            receipt_waiter=AsyncMock(return_value=receipt()),
            receipt_timeout_seconds=1,
            timeout_seconds=3,
            http_resources_factory=factory,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.BLOCKED)
        self.assertEqual(result.reason, "link_rehearsal_snapshot_unavailable")
        factory.assert_not_called()
        self.assertTrue(oauth.closed)
        self.assertNotIn("secret detail", repr(result))

    async def test_invalid_scope_never_requests_token_but_closes_oauth(self):
        oauth = OAuthResources()
        oauth.member_id = "different-member"

        result = await rehearse_controlled_link_with_injected_oauth(
            preview=preview(),
            settings=load_settings({}),
            oauth_resources=oauth,
            receipt_waiter=AsyncMock(return_value=receipt()),
            receipt_timeout_seconds=1,
            timeout_seconds=3,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.BLOCKED)
        self.assertEqual(result.reason, "link_rehearsal_scope_or_window_invalid")
        oauth.oauth_provider.get_access_token.assert_not_awaited()
        self.assertTrue(oauth.closed)


if __name__ == "__main__":
    unittest.main()
