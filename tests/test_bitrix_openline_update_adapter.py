import json
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from bitrix_connector.openline_link_rehearsal import CONTROLLED_BOT_ID
from bitrix_connector.openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_GET_PATH,
    BitrixOpenLinePreflightClient,
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    build_controlled_pilot_preview,
)
from bitrix_connector.openline_update_adapter import (
    BITRIX_OPENLINE_CONFIG_UPDATE_PATH,
    BitrixOpenLineUpdateClient,
    OneShotVerifiedOpenLineUpdate,
    OpenLineUpdateDecision,
    VerifiedUpdateStatus,
)


def config_payload(bot_id=CONTROLLED_BOT_ID):
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


def update_preview(*, link=True):
    original = OpenLineConfigSnapshot.model_validate(config_payload(245339))
    preflight = OpenLinePreflightResult(
        status=OpenLinePreflightStatus.READY,
        reason="openline_snapshot_ready",
        chat_id=78733,
        dialog_id="chat78733",
        config=original,
    )
    now = datetime(2026, 7, 27, 15, 0, tzinfo=timezone.utc)
    pilot = build_controlled_pilot_preview(
        preflight=preflight,
        bot_id=CONTROLLED_BOT_ID,
        member_id="member-controlled",
        webhook_url="https://nia.example.com/bitrix-connector/webhook",
        valid_from=now,
        valid_until=now + timedelta(minutes=10),
    )
    return pilot.link if link else pilot.rollback


class OpenLineUpdateAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_exact_payload_then_verifies_with_config_get(self):
        captured = []

        async def handler(request):
            payload = json.loads(request.content)
            captured.append((request.method, request.url.path, payload))
            if request.url.path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH:
                return httpx.Response(200, json={"result": True})
            return httpx.Response(
                200,
                json={"result": config_payload()},
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        update_client = BitrixOpenLineUpdateClient(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http,
        )
        read_client = BitrixOpenLinePreflightClient(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http,
        )
        result = await OneShotVerifiedOpenLineUpdate(
            update_client,
            read_client,
        ).apply(update_preview())

        self.assertEqual(result.status, VerifiedUpdateStatus.VERIFIED)
        self.assertTrue(result.verified)
        self.assertEqual(
            captured,
            [
                (
                    "POST",
                    BITRIX_OPENLINE_CONFIG_UPDATE_PATH,
                    {
                        "CONFIG_ID": 13,
                        "PARAMS": {
                            "WELCOME_BOT_ENABLE": "Y",
                            "WELCOME_BOT_JOIN": "always",
                            "WELCOME_BOT_ID": CONTROLLED_BOT_ID,
                            "WELCOME_BOT_TIME": 0,
                            "WELCOME_BOT_LEFT": "close",
                        },
                        "auth": "oauth-secret-token",
                    },
                ),
                (
                    "POST",
                    BITRIX_OPENLINE_CONFIG_GET_PATH,
                    {
                        "CONFIG_ID": 13,
                        "WITH_QUEUE": "N",
                        "SHOW_OFFLINE": "N",
                        "auth": "oauth-secret-token",
                    },
                ),
            ],
        )
        self.assertNotIn("oauth-secret-token", repr(result))

    async def test_one_shot_instance_refuses_second_update(self):
        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            if request.url.path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH:
                return httpx.Response(200, json={"result": True})
            return httpx.Response(200, json={"result": config_payload()})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        adapter = OneShotVerifiedOpenLineUpdate(
            BitrixOpenLineUpdateClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http,
            ),
            BitrixOpenLinePreflightClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http,
            ),
        )

        first = await adapter.apply(update_preview())
        second = await adapter.apply(update_preview())

        self.assertEqual(first.status, VerifiedUpdateStatus.VERIFIED)
        self.assertEqual(second.status, VerifiedUpdateStatus.ALREADY_USED)
        self.assertFalse(second.update_attempted)
        self.assertEqual(calls, 2)

    async def test_transport_and_ambiguous_responses_are_uncertain_no_retry(self):
        cases = (
            httpx.ReadTimeout("timeout"),
            httpx.Response(503, json={"error": "QUERY_LIMIT_EXCEEDED"}),
            httpx.Response(200, json={"unexpected": True}),
        )
        for response in cases:
            with self.subTest(response=type(response).__name__):
                calls = 0

                async def handler(request, current=response):
                    nonlocal calls
                    calls += 1
                    if isinstance(current, Exception):
                        raise current
                    return current

                http = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
                client = BitrixOpenLineUpdateClient(
                    portal_url="https://portal.bitrix24.test",
                    access_token="token",
                    timeout_seconds=3,
                    http_client=http,
                )
                result = await client.update(update_preview())
                await http.aclose()
                self.assertEqual(result.decision, OpenLineUpdateDecision.UNCERTAIN)
                self.assertEqual(calls, 1)

    async def test_false_result_is_failed_without_readback(self):
        paths = []

        async def handler(request):
            paths.append(request.url.path)
            return httpx.Response(200, json={"result": False})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        adapter = OneShotVerifiedOpenLineUpdate(
            BitrixOpenLineUpdateClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http,
            ),
            BitrixOpenLinePreflightClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http,
            ),
        )
        result = await adapter.apply(update_preview())

        self.assertEqual(result.status, VerifiedUpdateStatus.FAILED)
        self.assertFalse(result.config_read_attempted)
        self.assertEqual(paths, [BITRIX_OPENLINE_CONFIG_UPDATE_PATH])

    async def test_readback_mismatch_is_conflict(self):
        async def handler(request):
            if request.url.path == BITRIX_OPENLINE_CONFIG_UPDATE_PATH:
                return httpx.Response(200, json={"result": True})
            return httpx.Response(
                200,
                json={"result": config_payload(bot_id=245339)},
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        result = await OneShotVerifiedOpenLineUpdate(
            BitrixOpenLineUpdateClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http,
            ),
            BitrixOpenLinePreflightClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http,
            ),
        ).apply(update_preview())

        self.assertEqual(result.status, VerifiedUpdateStatus.CONFLICT)
        self.assertFalse(result.verified)

    def test_client_surface_has_only_fixed_update_and_close(self):
        public = {
            name
            for name in dir(BitrixOpenLineUpdateClient)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"close", "update"})


if __name__ == "__main__":
    unittest.main()
