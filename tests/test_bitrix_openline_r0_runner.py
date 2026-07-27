import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import httpx

from bitrix_connector.config import load_settings
from bitrix_connector.openline_link_composition import OpenLineLinkHttpResources
from bitrix_connector.openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    LinkRehearsalStatus,
)
from bitrix_connector.openline_r0_receipt import ControlledR0Receipt
from bitrix_connector.openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_GET_PATH,
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    BitrixOpenLinePreflightClient,
)
from bitrix_connector.openline_r0_runner import (
    CONTROLLED_R0_CONFIRMATION,
    ControlledR0RunnerStatus,
    execute_controlled_r0_runner,
)
from bitrix_connector.openline_update_adapter import (
    BITRIX_OPENLINE_CONFIG_UPDATE_PATH,
    BitrixOpenLineUpdateClient,
)


NOW = datetime(2026, 7, 27, 19, 0, tzinfo=timezone.utc)
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


def fresh_preflight(bot_id=245339):
    return OpenLinePreflightResult(
        status=OpenLinePreflightStatus.READY,
        reason="openline_snapshot_ready",
        chat_id=78733,
        dialog_id="chat78733",
        config=OpenLineConfigSnapshot.model_validate(config_payload(bot_id)),
    )


class ReceiptGate:
    def __init__(self):
        self.rule = None
        self.closed = False

    async def arm(self, rule):
        self.rule = rule

    async def wait(self):
        return ControlledR0Receipt(
            event_key="a" * 64,
            member_id=self.rule.member_id,
            bot_id=self.rule.bot_id,
            chat_id=self.rule.chat_id,
            dialog_id=self.rule.dialog_id,
            effective_mode="off",
            activation_locked=True,
            external_calls_enabled=False,
            identity_verified=True,
            persisted=False,
            nia_called=False,
            bitrix_written=False,
        )

    async def close(self):
        self.closed = True


class OAuthResources:
    def __init__(self):
        self.member_id = MEMBER_ID
        self.portal_url = "https://portal.bitrix24.test"
        self.oauth_provider = AsyncMock()
        self.oauth_provider.get_access_token.return_value = "oauth-secret"
        self.closed = False

    async def close(self):
        self.closed = True


class OAuthFactory:
    def __init__(self, resources):
        self.resources = resources
        self.calls = []

    async def build(self, settings, *, timeout_seconds):
        self.calls.append((settings, timeout_seconds))
        return self.resources


class ControlledR0RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_receipt_gate_blocks_before_oauth(self):
        factory = Mock()
        result = await execute_controlled_r0_runner(
            confirmation=CONTROLLED_R0_CONFIRMATION,
            settings=load_settings({}),
            resources_factory=factory,
            clock=lambda: NOW,
        )
        self.assertEqual(result.status, ControlledR0RunnerStatus.BLOCKED)
        self.assertEqual(result.reason, "r0_receipt_gate_required")
        factory.build.assert_not_called()

    async def test_fresh_preflight_delegates_and_restores_with_one_token(self):
        current_bot = 245339
        calls = []

        async def handler(request):
            nonlocal current_bot
            payload = json.loads(request.content)
            calls.append((request.url.path, payload))
            if request.url.path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH:
                current_bot = payload["PARAMS"]["WELCOME_BOT_ID"]
                return httpx.Response(200, json={"result": True})
            return httpx.Response(200, json={"result": config_payload(current_bot)})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)

        def http_factory(*, portal_url, access_token, timeout_seconds):
            return OpenLineLinkHttpResources(
                link_update_client=BitrixOpenLineUpdateClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=http,
                ),
                link_read_client=BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=http,
                ),
                rollback_update_client=BitrixOpenLineUpdateClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=http,
                ),
                rollback_read_client=BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=http,
                ),
            )

        resources = OAuthResources()
        receipt_gate = ReceiptGate()
        preflight = AsyncMock(return_value=fresh_preflight())
        result = await execute_controlled_r0_runner(
            confirmation=CONTROLLED_R0_CONFIRMATION,
            settings=load_settings({"NIA_BITRIX_MODE": "active"}),
            receipt_gate=receipt_gate,
            resources_factory=OAuthFactory(resources),
            preflight_once=preflight,
            http_resources_factory=http_factory,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, ControlledR0RunnerStatus.RESTORED)
        self.assertTrue(result.preflight_completed)
        self.assertTrue(result.delegated)
        self.assertTrue(result.rollback_verified)
        self.assertTrue(result.receipt_verified)
        self.assertEqual(current_bot, 245339)
        resources.oauth_provider.get_access_token.assert_awaited_once_with(MEMBER_ID)
        preflight.assert_awaited_once_with(
            portal_url=resources.portal_url,
            access_token="oauth-secret",
            timeout_seconds=10.0,
        )
        self.assertEqual(
            [payload["PARAMS"]["WELCOME_BOT_ID"] for path, payload in calls if path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH],
            [CONTROLLED_BOT_ID, 245339],
        )
        self.assertTrue(resources.closed)
        self.assertTrue(receipt_gate.closed)
        self.assertNotIn("oauth-secret", repr(result))

    async def test_wrong_confirmation_never_builds_oauth(self):
        factory = Mock()
        result = await execute_controlled_r0_runner(
            confirmation="VINCULAR",
            settings=load_settings({}),
            resources_factory=factory,
            clock=lambda: NOW,
        )
        self.assertEqual(result.status, ControlledR0RunnerStatus.BLOCKED)
        self.assertEqual(result.reason, "r0_confirmation_mismatch")
        factory.build.assert_not_called()

    async def test_drifted_fresh_snapshot_blocks_and_closes_without_composition(self):
        resources = OAuthResources()
        composition = AsyncMock()
        result = await execute_controlled_r0_runner(
            confirmation=CONTROLLED_R0_CONFIRMATION,
            settings=load_settings({}),
            receipt_gate=ReceiptGate(),
            resources_factory=OAuthFactory(resources),
            preflight_once=AsyncMock(return_value=fresh_preflight(999999)),
            composition=composition,
            clock=lambda: NOW,
        )
        self.assertEqual(result.status, ControlledR0RunnerStatus.BLOCKED)
        self.assertEqual(result.reason, "r0_fresh_preflight_not_exact")
        self.assertTrue(result.preflight_completed)
        self.assertFalse(result.delegated)
        composition.assert_not_awaited()
        self.assertTrue(resources.closed)

    async def test_runner_reduces_resource_failure_to_safe_result(self):
        resources = OAuthResources()
        resources.oauth_provider.get_access_token.side_effect = RuntimeError(
            "secret internal detail"
        )
        result = await execute_controlled_r0_runner(
            confirmation=CONTROLLED_R0_CONFIRMATION,
            settings=load_settings({}),
            receipt_gate=ReceiptGate(),
            resources_factory=OAuthFactory(resources),
            clock=lambda: NOW,
        )
        self.assertEqual(result.status, ControlledR0RunnerStatus.BLOCKED)
        self.assertEqual(result.reason, "r0_runner_failed_safe")
        self.assertTrue(resources.closed)
        self.assertNotIn("secret internal detail", repr(result))


if __name__ == "__main__":
    unittest.main()
