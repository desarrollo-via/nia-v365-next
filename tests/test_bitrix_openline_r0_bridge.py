import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from bitrix_connector.config import load_settings
from bitrix_connector.g0_entrypoint import G0_WEBHOOK_PATH, create_g0_entrypoint
from bitrix_connector.openline_r0_bridge import (
    InMemoryR0ReceiptBridge,
    R0BridgeArmRequest,
    R0BridgeCode,
    R0_BRIDGE_PREFIX,
)
from bitrix_connector.openline_r0_bridge_mount import (
    build_optional_r0_bridge_mount,
)
from bitrix_connector.openline_r0_bridge_client import HttpR0ReceiptGate
from bitrix_connector.openline_link_composition import OpenLineLinkHttpResources
from bitrix_connector.openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_GET_PATH,
    BitrixOpenLinePreflightClient,
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
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
from bitrix_connector.pilot_scope import PilotScopeRule


TOKEN = "review-token-controlado-123456789"
RUN_ID = "b" * 64
NOW = datetime(2026, 7, 27, 21, 0, tzinfo=timezone.utc)


def safe_settings():
    return load_settings({
        "NIA_BITRIX_MODE": "active",
        "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
        "NIA_BITRIX_MEMBER_ID": "member-controlled",
        "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
    })


def bridge_settings():
    return load_settings({
        "NIA_BITRIX_MODE": "off",
        "NIA_BITRIX_G0_PUBLIC_ORIGIN": "https://nia.example.test",
        "NIA_BITRIX_R0_BRIDGE_ENABLED": "true",
        "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
        "NIA_BITRIX_MEMBER_ID": "member-controlled",
        "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        "NIA_BITRIX_REVIEW_TOKEN": TOKEN,
        "NIA_BITRIX_REVIEW_ACTOR": "hugo",
        "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "reviewer:hugo:r0",
    })


def scope_rule(*, valid_until=None):
    return PilotScopeRule(
        member_id="member-controlled",
        bot_id=373259,
        chat_id=78733,
        dialog_id="chat78733",
        valid_from=NOW - timedelta(minutes=1),
        valid_until=valid_until or NOW + timedelta(minutes=9),
    )


def webhook_form(*, chat_id=78733, dialog_id="chat78733"):
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "373259",
        "data[message][id]": "9100",
        "data[message][chatId]": str(chat_id),
        "data[message][authorId]": "27",
        "data[message][text]": "mensaje real controlado",
        "data[chat][dialogId]": dialog_id,
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": "member-controlled",
        "auth[application_token]": "application-secret",
    }


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


def fresh_preflight():
    return OpenLinePreflightResult(
        status=OpenLinePreflightStatus.READY,
        reason="openline_snapshot_ready",
        chat_id=78733,
        dialog_id="chat78733",
        config=OpenLineConfigSnapshot.model_validate(config_payload()),
    )


class OAuthResources:
    def __init__(self):
        self.member_id = "member-controlled"
        self.portal_url = "https://portal.bitrix24.test"
        self.oauth_provider = AsyncMock()
        self.oauth_provider.get_access_token.return_value = "oauth-secret"
        self.closed = False

    async def close(self):
        self.closed = True


class OAuthFactory:
    def __init__(self, resources):
        self.resources = resources

    async def build(self, settings, *, timeout_seconds):
        return self.resources


def build_app(bridge):
    settings = bridge_settings()
    mount = build_optional_r0_bridge_mount(
        settings,
        bridge_factory=lambda: bridge,
    )
    app = create_g0_entrypoint(
        public_origin="https://nia.example.test",
        settings_loader=lambda: settings,
        receipt_observer=mount.receipt_observer,
        optional_router=mount.router,
    )
    return app


class R0ReceiptBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = InMemoryR0ReceiptBridge(clock=lambda: NOW)
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=build_app(self.bridge)),
            base_url="https://nia.example.test",
        )

    async def asyncTearDown(self):
        await self.http.aclose()

    async def test_client_arms_queries_and_consumes_exact_webhook_receipt(self):
        gate = HttpR0ReceiptGate(
            public_origin="https://nia.example.test",
            review_token=TOKEN,
            poll_interval_seconds=0.001,
            http_client=self.http,
            run_id_factory=lambda: RUN_ID,
        )
        await gate.arm(scope_rule())
        waiter = asyncio.create_task(gate.wait())

        wrong = await self.http.post(
            G0_WEBHOOK_PATH,
            data=webhook_form(chat_id=78734, dialog_id="chat78734"),
        )
        self.assertEqual(wrong.status_code, 200)

        exact = await self.http.post(G0_WEBHOOK_PATH, data=webhook_form())
        self.assertEqual(exact.status_code, 200)
        receipt = await asyncio.wait_for(waiter, timeout=0.2)

        self.assertEqual(receipt.event_key, exact.json()["event_key"])
        self.assertEqual(receipt.bot_id, 373259)
        self.assertEqual(receipt.chat_id, 78733)
        self.assertEqual(receipt.dialog_id, "chat78733")
        self.assertFalse(receipt.persisted)
        self.assertFalse(receipt.nia_called)
        self.assertFalse(receipt.bitrix_written)
        self.assertNotIn("mensaje real controlado", repr(receipt))
        self.assertNotIn("application-secret", repr(receipt))

        consumed = await self.http.get(
            f"{R0_BRIDGE_PREFIX}/{RUN_ID}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        self.assertEqual(consumed.status_code, 404)
        await gate.close()

    async def test_full_runner_consumes_web_receipt_and_restores(self):
        current_bot = 245339
        webhook_sent = False

        async def bitrix_handler(request):
            nonlocal current_bot, webhook_sent
            if request.url.path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH:
                payload = json.loads(request.content)
                current_bot = payload["PARAMS"]["WELCOME_BOT_ID"]
                return httpx.Response(200, json={"result": True})
            self.assertEqual(request.url.path, BITRIX_OPENLINE_CONFIG_GET_PATH)
            if current_bot == 373259 and not webhook_sent:
                webhook_sent = True
                asyncio.create_task(
                    self.http.post(G0_WEBHOOK_PATH, data=webhook_form())
                )
            return httpx.Response(200, json={"result": config_payload(current_bot)})

        bitrix_http = httpx.AsyncClient(
            transport=httpx.MockTransport(bitrix_handler)
        )
        self.addAsyncCleanup(bitrix_http.aclose)

        def http_factory(*, portal_url, access_token, timeout_seconds):
            return OpenLineLinkHttpResources(
                link_update_client=BitrixOpenLineUpdateClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=bitrix_http,
                ),
                link_read_client=BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=bitrix_http,
                ),
                rollback_update_client=BitrixOpenLineUpdateClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=bitrix_http,
                ),
                rollback_read_client=BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=timeout_seconds,
                    http_client=bitrix_http,
                ),
            )

        gate = HttpR0ReceiptGate(
            public_origin="https://nia.example.test",
            review_token=TOKEN,
            poll_interval_seconds=0.001,
            http_client=self.http,
            run_id_factory=lambda: RUN_ID,
        )
        resources = OAuthResources()
        result = await execute_controlled_r0_runner(
            confirmation=CONTROLLED_R0_CONFIRMATION,
            settings=safe_settings(),
            receipt_gate=gate,
            receipt_timeout_seconds=1,
            resources_factory=OAuthFactory(resources),
            preflight_once=AsyncMock(return_value=fresh_preflight()),
            http_resources_factory=http_factory,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, ControlledR0RunnerStatus.RESTORED)
        self.assertTrue(result.receipt_verified)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(current_bot, 245339)
        self.assertTrue(webhook_sent)
        self.assertTrue(resources.closed)

    async def test_authentication_precedes_json_and_single_session_conflicts(self):
        unauthorized = await self.http.post(
            f"{R0_BRIDGE_PREFIX}/arm",
            headers={
                "Authorization": "Bearer incorrecto",
                "Content-Type": "application/json",
            },
            content=b'{"json":',
        )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.json()["code"], "review_unauthorized")

        malformed = await self.http.post(
            f"{R0_BRIDGE_PREFIX}/arm",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            content=b'{"json":',
        )
        self.assertEqual(malformed.status_code, 422)

        first = R0BridgeArmRequest(
            run_id=RUN_ID,
            member_id="member-controlled",
            valid_from=NOW - timedelta(minutes=1),
            valid_until=NOW + timedelta(minutes=9),
        )
        self.assertEqual((await self.bridge.arm(first)).code, R0BridgeCode.ARMED)
        second = first.model_copy(update={"run_id": "c" * 64})
        self.assertEqual(
            (await self.bridge.arm(second)).code,
            R0BridgeCode.CONFLICT,
        )

    async def test_close_disarms_pending_session_and_hides_credentials(self):
        gate = HttpR0ReceiptGate(
            public_origin="https://nia.example.test",
            review_token=TOKEN,
            http_client=self.http,
            run_id_factory=lambda: RUN_ID,
        )
        await gate.arm(scope_rule())
        evidence = repr(gate.__dict__)
        self.assertNotIn(TOKEN, evidence)
        self.assertNotIn(RUN_ID, evidence)

        await gate.close()
        missing = await self.http.get(
            f"{R0_BRIDGE_PREFIX}/{RUN_ID}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        self.assertEqual(missing.status_code, 404)

    async def test_expired_session_is_removed_without_background_job(self):
        current = NOW
        bridge = InMemoryR0ReceiptBridge(clock=lambda: current)
        request = R0BridgeArmRequest(
            run_id=RUN_ID,
            member_id="member-controlled",
            valid_from=NOW - timedelta(minutes=1),
            valid_until=NOW + timedelta(minutes=1),
        )
        self.assertEqual((await bridge.arm(request)).code, R0BridgeCode.ARMED)
        current = NOW + timedelta(minutes=2)
        self.assertEqual(
            (await bridge.inspect(RUN_ID)).code,
            R0BridgeCode.EXPIRED,
        )
        self.assertEqual(
            (await bridge.inspect(RUN_ID)).code,
            R0BridgeCode.NOT_FOUND,
        )

    def test_bridge_does_not_enter_main_or_duplicate_full_prefix(self):
        root = Path(__file__).parents[1]
        main_source = (root / "main.py").read_text(encoding="utf-8")
        router_source = (
            root / "bitrix_connector" / "router.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("build_r0_receipt_bridge_router", main_source)
        self.assertNotIn(R0_BRIDGE_PREFIX, main_source)
        self.assertNotIn("build_r0_receipt_bridge_router", router_source)
        self.assertNotIn(R0_BRIDGE_PREFIX, router_source)
        self.assertIn("build_optional_r0_bridge_mount", router_source)
        self.assertIn("R0_BRIDGE_EMBEDDED_PREFIX", router_source)


if __name__ == "__main__":
    unittest.main()
