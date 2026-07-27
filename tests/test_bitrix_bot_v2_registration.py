import json
import unittest

import httpx

from bitrix_connector.bot_v2_preflight import (
    BotV2PreflightResult,
    BotV2PreflightStatus,
    BotV2RegistrationPreview,
    build_controlled_registration_preview,
)
from bitrix_connector.bot_v2_registration import (
    BITRIX_V2_BOT_REGISTER_PATH,
    BitrixBotV2RegistrationClient,
    ControlledBotRegistrationRunner,
    ControlledRegistrationStatus,
)


WEBHOOK = "https://bot.example.com/bitrix-connector/webhook"


def ready_preflight():
    return BotV2PreflightResult(
        status=BotV2PreflightStatus.READY,
        reason="bot_v2_preflight_no_existing_bot",
        rest_revision=35,
        registration_needed=True,
    )


def compatible_preflight(bot_id=456):
    return BotV2PreflightResult(
        status=BotV2PreflightStatus.EXISTING_COMPATIBLE,
        reason="bot_v2_preflight_existing_compatible",
        rest_revision=35,
        existing_bot_id=bot_id,
    )


def registered_bot(bot_id=456, **overrides):
    value = {
        "id": bot_id,
        "code": "nia_next_openline_controlled",
        "type": "openline",
        "isSupportOpenline": True,
        "eventMode": "webhook",
        "webhookUrl": WEBHOOK,
        "isHidden": True,
        "isReactionsEnabled": False,
    }
    value.update(overrides)
    return value


class RegistrationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_only_exact_registration_contract(self):
        captured = []

        async def handler(request):
            captured.append(
                (request.method, request.url.path, json.loads(request.content))
            )
            return httpx.Response(
                200,
                json={"result": {"bot": registered_bot()}},
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2RegistrationClient(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http_client,
        )
        result = await ControlledBotRegistrationRunner(client).run(
            preflight=ready_preflight(),
            preview=build_controlled_registration_preview(WEBHOOK),
        )

        self.assertEqual(result.status, ControlledRegistrationStatus.REGISTERED)
        self.assertEqual(result.bot_id, 456)
        self.assertTrue(result.registration_attempted)
        self.assertEqual(len(captured), 1)
        method, path, payload = captured[0]
        self.assertEqual((method, path), ("POST", BITRIX_V2_BOT_REGISTER_PATH))
        self.assertEqual(payload["auth"], "oauth-secret-token")
        self.assertEqual(
            payload["fields"],
            build_controlled_registration_preview(WEBHOOK).fields.model_dump(
                mode="json"
            ),
        )
        self.assertNotIn("oauth-secret-token", repr(result))
        self.assertEqual(
            result.unregister_preview.model_dump(mode="json"),
            {
                "method": "imbot.v2.Bot.unregister",
                "executable": False,
                "requires_explicit_authorization": True,
                "botId": 456,
            },
        )

    async def test_second_run_is_idempotent_without_another_mutation(self):
        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={"result": {"bot": registered_bot(812)}},
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2RegistrationClient(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http_client,
        )
        runner = ControlledBotRegistrationRunner(client)
        preview = build_controlled_registration_preview(WEBHOOK)

        first = await runner.run(preflight=ready_preflight(), preview=preview)
        second = await runner.run(
            preflight=compatible_preflight(first.bot_id),
            preview=preview,
        )

        self.assertEqual(first.status, ControlledRegistrationStatus.REGISTERED)
        self.assertEqual(second.status, ControlledRegistrationStatus.IDEMPOTENT)
        self.assertEqual((first.bot_id, second.bot_id), (812, 812))
        self.assertFalse(second.registration_attempted)
        self.assertEqual(calls, 1)

    async def test_fails_closed_on_conflicting_response(self):
        async def handler(request):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "bot": registered_bot(
                            code="unexpected_bot",
                            isHidden=False,
                        )
                    }
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2RegistrationClient(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http_client,
        )
        result = await ControlledBotRegistrationRunner(client).run(
            preflight=ready_preflight(),
            preview=build_controlled_registration_preview(WEBHOOK),
        )

        self.assertEqual(result.status, ControlledRegistrationStatus.FAILED)
        self.assertEqual(result.reason, "bot_v2_registration_result_conflict")
        self.assertIsNone(result.unregister_preview)

    async def test_remote_failures_are_safe(self):
        cases = (
            (401, {"error": "expired_token", "error_description": "secret"}, "retry"),
            (429, {"error": "QUERY_LIMIT_EXCEEDED"}, "retry"),
            (403, {"error": "ACCESS_DENIED", "error_description": "secret"}, "failed"),
            (200, {"result": {}}, "failed"),
        )
        for status, body, expected in cases:
            with self.subTest(status=status, body=body):
                async def handler(request, current_status=status, current_body=body):
                    return httpx.Response(current_status, json=current_body)

                http_client = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
                client = BitrixBotV2RegistrationClient(
                    portal_url="https://portal.bitrix24.test",
                    access_token="secret",
                    timeout_seconds=3,
                    http_client=http_client,
                )
                result = await ControlledBotRegistrationRunner(client).run(
                    preflight=ready_preflight(),
                    preview=build_controlled_registration_preview(WEBHOOK),
                )
                await http_client.aclose()
                self.assertEqual(result.status.value, expected)
                self.assertNotIn("secret", repr(result))

    async def test_rejects_non_ready_preflight_before_network(self):
        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixBotV2RegistrationClient(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http_client,
        )
        blocked = BotV2PreflightResult(
            status=BotV2PreflightStatus.EXISTING_CONFLICT,
            reason="conflict",
        )
        result = await ControlledBotRegistrationRunner(client).run(
            preflight=blocked,
            preview=build_controlled_registration_preview(WEBHOOK),
        )

        self.assertEqual(result.status, ControlledRegistrationStatus.FAILED)
        self.assertFalse(result.registration_attempted)
        self.assertEqual(calls, 0)

    def test_public_surface_cannot_unregister_or_call_arbitrary_methods(self):
        public = {
            name
            for name in dir(BitrixBotV2RegistrationClient)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"close", "register"})

    async def test_rejects_modified_preview(self):
        original = build_controlled_registration_preview(WEBHOOK)
        modified = BotV2RegistrationPreview(
            method=original.method,
            executable=False,
            fields=original.fields.model_copy(update={"code": "other_bot"}),
        )
        client = BitrixBotV2RegistrationClient(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: None)
            ),
        )
        self.addAsyncCleanup(client._http_client.aclose)

        with self.assertRaisesRegex(
            ValueError,
            "bot_v2_registration_preview_not_controlled",
        ):
            await ControlledBotRegistrationRunner(client).run(
                preflight=ready_preflight(),
                preview=modified,
            )


if __name__ == "__main__":
    unittest.main()
