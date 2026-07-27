import json
import unittest

import httpx

from bitrix_connector.bot_v2_preflight import (
    BITRIX_V2_BOT_LIST_PATH,
    BITRIX_V2_REVISION_PATH,
    BitrixBotV2PreflightClient,
    BotV2PreflightInspector,
    BotV2PreflightStatus,
    build_controlled_registration_preview,
)


class BitrixBotV2PreflightClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_only_exact_read_methods_and_redacts_token(self):
        captured = []

        async def handler(request):
            payload = json.loads(request.content)
            captured.append((request.method, request.url.path, payload))
            if request.url.path.endswith(BITRIX_V2_REVISION_PATH):
                return httpx.Response(
                    200,
                    json={
                        "result": {
                            "rest": 33,
                            "web": 130,
                            "mobile": 23,
                            "desktop": 6,
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "result": {
                        "bots": [],
                        "users": [],
                        "hasNextPage": False,
                    }
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2PreflightClient(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http_client,
        )

        result = await BotV2PreflightInspector(client).inspect()

        self.assertEqual(result.status, BotV2PreflightStatus.READY)
        self.assertTrue(result.registration_needed)
        self.assertEqual(result.rest_revision, 33)
        self.assertEqual(
            [item[:2] for item in captured],
            [
                ("POST", BITRIX_V2_REVISION_PATH),
                ("POST", BITRIX_V2_BOT_LIST_PATH),
            ],
        )
        self.assertEqual(captured[0][2], {"auth": "oauth-secret-token"})
        self.assertEqual(
            captured[1][2],
            {
                "filter": {"type": "openline"},
                "limit": 50,
                "offset": 0,
                "auth": "oauth-secret-token",
            },
        )
        self.assertNotIn("oauth-secret-token", repr(result))

    async def test_existing_bot_is_compatible_or_conflict(self):
        for bot, expected in (
            (
                {
                    "id": 456,
                    "code": "nia_next_openline_controlled",
                    "type": "openline",
                    "isSupportOpenline": True,
                    "eventMode": "webhook",
                    "isHidden": True,
                    "isReactionsEnabled": False,
                },
                BotV2PreflightStatus.EXISTING_COMPATIBLE,
            ),
            (
                {
                    "id": 457,
                    "code": "nia_next_openline_controlled",
                    "type": "bot",
                    "isSupportOpenline": False,
                    "eventMode": "fetch",
                    "isHidden": False,
                    "isReactionsEnabled": True,
                },
                BotV2PreflightStatus.EXISTING_CONFLICT,
            ),
        ):
            async def handler(request, current=bot):
                if request.url.path.endswith(BITRIX_V2_REVISION_PATH):
                    return httpx.Response(
                        200,
                        json={"result": {"rest": 33, "web": 1, "mobile": 1, "desktop": 1}},
                    )
                return httpx.Response(
                    200,
                    json={"result": {"bots": [current], "hasNextPage": False}},
                )

            http_client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            )
            self.addAsyncCleanup(http_client.aclose)
            client = BitrixBotV2PreflightClient(
                portal_url="https://portal.bitrix24.test",
                access_token="token",
                timeout_seconds=3,
                http_client=http_client,
            )
            result = await BotV2PreflightInspector(client).inspect()
            self.assertEqual(result.status, expected)
            self.assertFalse(result.registration_needed)

    async def test_failures_are_safe_and_stop_the_sequence(self):
        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(
                401,
                json={
                    "error": "NO_AUTH_FOUND",
                    "error_description": "oauth-secret-token",
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2PreflightClient(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http_client,
        )

        result = await BotV2PreflightInspector(client).inspect()

        self.assertEqual(result.status, BotV2PreflightStatus.FAILED)
        self.assertEqual(calls, 1)
        self.assertNotIn("oauth-secret-token", repr(result))

    async def test_expired_token_has_a_refreshable_safe_reason(self):
        async def handler(request):
            return httpx.Response(
                401,
                json={
                    "error": "expired_token",
                    "error_description": "oauth-secret-token",
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2PreflightClient(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http_client,
        )

        result = await BotV2PreflightInspector(client).inspect()

        self.assertEqual(result.status, BotV2PreflightStatus.RETRY)
        self.assertEqual(result.reason, "bot_v2_preflight_token_expired")
        self.assertNotIn("oauth-secret-token", repr(result))

    def test_public_client_surface_has_no_registration_method(self):
        public = {
            name
            for name in dir(BitrixBotV2PreflightClient)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"close", "get_revision", "list_bots"})


class BotV2RegistrationPreviewTests(unittest.TestCase):
    def test_builds_exact_non_executable_contract(self):
        preview = build_controlled_registration_preview(
            "https://bot.example.com/bitrix-connector/webhook"
        )

        self.assertEqual(preview.method, "imbot.v2.Bot.register")
        self.assertFalse(preview.executable)
        self.assertEqual(
            preview.model_dump(mode="json")["fields"],
            {
                "code": "nia_next_openline_controlled",
                "properties": {
                    "name": "NIA Next Controlado",
                    "workPosition": "Piloto supervisado",
                },
                "type": "openline",
                "isSupportOpenline": True,
                "eventMode": "webhook",
                "webhookUrl": "https://bot.example.com/bitrix-connector/webhook",
                "isHidden": True,
                "isReactionsEnabled": False,
            },
        )

    def test_rejects_temporary_or_non_exact_webhook_urls(self):
        for url in (
            "http://bot.example.com/bitrix-connector/webhook",
            "https://localhost/bitrix-connector/webhook",
            "https://203.0.113.10/bitrix-connector/webhook",
            "https://demo.trycloudflare.com/bitrix-connector/webhook",
            "https://bot.example.com/other",
            "https://bot.example.com/bitrix-connector/webhook?secret=x",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(
                    ValueError,
                    "bot_v2_stable_webhook_url_invalid",
                ):
                    build_controlled_registration_preview(url)


if __name__ == "__main__":
    unittest.main()
