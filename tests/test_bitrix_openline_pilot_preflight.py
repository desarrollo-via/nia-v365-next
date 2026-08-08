import json
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from bitrix_connector.openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_GET_PATH,
    BITRIX_OPENLINE_DIALOG_GET_PATH,
    BitrixOpenLinePreflightClient,
    OpenLineConfigSnapshot,
    OpenLineDialog,
    OpenLinePreflightInspector,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    OpenLineReadDecision,
    build_controlled_pilot_preview,
)


def config_payload(**overrides):
    values = {
        "ID": "13",
        "LINE_NAME": "WhatApp Wazzup OFICIAL",
        "ACTIVE": "Y",
        "WELCOME_BOT_ENABLE": "Y",
        "WELCOME_BOT_JOIN": "always",
        "WELCOME_BOT_ID": "245339",
        "WELCOME_BOT_TIME": "0",
        "WELCOME_BOT_LEFT": "close",
        "NO_ANSWER_BOT_ID": "0",
        "CLOSE_BOT_ID": "0",
        "AUTO_CLOSE_BOT_ID": "0",
        "WORKTIME_DAYOFF_BOT_ID": "0",
    }
    values.update(overrides)
    return values


class OpenLineClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_exact_endpoints_and_minimal_payloads(self):
        captured = []

        async def handler(request):
            captured.append((request.url.path, json.loads(request.content)))
            if request.url.path.endswith(BITRIX_OPENLINE_DIALOG_GET_PATH):
                return httpx.Response(
                    200,
                    json={"result": {
                        "id": 78733,
                        "dialog_id": "chat78733",
                        "entity_type": "LINES",
                        "entity_id": "wazzup|13|remote-chat|remote-user",
                        "name": "dato no proyectado",
                    }},
                )
            return httpx.Response(200, json={"result": config_payload(QUEUE=[1, 2])})

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixOpenLinePreflightClient(
            portal_url="https://portal.bitrix24.test/",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http_client,
        )
        dialog = await client.get_dialog(78733)
        config = await client.get_config(dialog.dialog.config_id)

        self.assertEqual(dialog.decision, OpenLineReadDecision.SUCCESS)
        self.assertEqual(config.decision, OpenLineReadDecision.SUCCESS)
        self.assertEqual(config.config.config_id, 13)
        self.assertEqual(captured, [
            (BITRIX_OPENLINE_DIALOG_GET_PATH, {
                "CHAT_ID": 78733,
                "auth": "oauth-secret-token",
            }),
            (BITRIX_OPENLINE_CONFIG_GET_PATH, {
                "CONFIG_ID": 13,
                "WITH_QUEUE": "N",
                "SHOW_OFFLINE": "N",
                "auth": "oauth-secret-token",
            }),
        ])
        self.assertNotIn("oauth-secret-token", repr(dialog))
        self.assertNotIn("dato no proyectado", repr(dialog))

    async def test_inspector_verifies_dialog_line_and_snapshot(self):
        async def handler(request):
            if request.url.path.endswith(BITRIX_OPENLINE_DIALOG_GET_PATH):
                return httpx.Response(200, json={"result": {
                    "id": 78733,
                    "dialog_id": "chat78733",
                    "entity_type": "LINES",
                    "entity_id": "wazzup|13|remote-chat|remote-user",
                }})
            return httpx.Response(200, json={"result": config_payload()})

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixOpenLinePreflightClient(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http_client,
        )
        result = await OpenLinePreflightInspector(client).inspect(
            chat_id=78733,
            dialog_id="chat78733",
        )

        self.assertEqual(result.status, OpenLinePreflightStatus.READY)
        self.assertEqual(result.config.config_id, 13)
        self.assertEqual(result.config.welcome_bot_id, 245339)

    async def test_inspector_reuses_preloaded_dialog_and_reads_only_config(self):
        captured = []

        async def handler(request):
            captured.append(request.url.path)
            return httpx.Response(200, json={"result": config_payload()})

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixOpenLinePreflightClient(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http_client,
        )
        result = await OpenLinePreflightInspector(client).inspect_dialog(
            dialog=OpenLineDialog(
                id=78733,
                dialog_id="chat78733",
                entity_type="LINES",
                entity_id="wazzup|13|remote-chat|remote-user",
            ),
            chat_id=78733,
            dialog_id="chat78733",
        )

        self.assertEqual(result.status, OpenLinePreflightStatus.READY)
        self.assertEqual(captured, [BITRIX_OPENLINE_CONFIG_GET_PATH])

    async def test_invalid_or_mismatched_data_fails_closed(self):
        cases = (
            ({"id": 78733, "dialog_id": "chat78733", "entity_type": "LINES", "entity_id": "bad"}, None, OpenLinePreflightStatus.FAILED),
            ({"id": 78734, "dialog_id": "chat78734", "entity_type": "LINES", "entity_id": "wazzup|13|x|y"}, None, OpenLinePreflightStatus.MISMATCH),
            ({"id": 78733, "dialog_id": "chat78733", "entity_type": "LINES", "entity_id": "wazzup|13|x|y"}, config_payload(ID="14"), OpenLinePreflightStatus.MISMATCH),
            ({"id": 78733, "dialog_id": "chat78733", "entity_type": "LINES", "entity_id": "wazzup|13|x|y"}, config_payload(ACTIVE="N"), OpenLinePreflightStatus.MISMATCH),
        )
        for dialog_payload, line_payload, expected in cases:
            with self.subTest(expected=expected, line=line_payload):
                async def handler(request, dialog=dialog_payload, line=line_payload):
                    if request.url.path.endswith(BITRIX_OPENLINE_DIALOG_GET_PATH):
                        return httpx.Response(200, json={"result": dialog})
                    return httpx.Response(200, json={"result": line})

                http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
                self.addAsyncCleanup(http_client.aclose)
                client = BitrixOpenLinePreflightClient(
                    portal_url="https://portal.bitrix24.test",
                    access_token="token",
                    timeout_seconds=3,
                    http_client=http_client,
                )
                result = await OpenLinePreflightInspector(client).inspect(
                    chat_id=78733,
                    dialog_id="chat78733",
                )
                self.assertEqual(result.status, expected)

    async def test_remote_failures_are_safe_and_retryable(self):
        responses = (
            (httpx.Response(429, headers={"Retry-After": "9"}), OpenLineReadDecision.RETRY, 9),
            (httpx.Response(401, json={"error": "expired_token", "error_description": "oauth-secret-token"}), OpenLineReadDecision.RETRY, 0),
            (httpx.Response(403, json={"error": "ACCESS_DENIED", "error_description": "private"}), OpenLineReadDecision.FAIL, 0),
        )
        for response, decision, retry_after in responses:
            async def handler(request, current=response):
                return current

            http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            self.addAsyncCleanup(http_client.aclose)
            client = BitrixOpenLinePreflightClient(
                portal_url="https://portal.bitrix24.test",
                access_token="oauth-secret-token",
                timeout_seconds=3,
                http_client=http_client,
            )
            result = await client.get_dialog(78733)
            self.assertEqual(result.decision, decision)
            self.assertEqual(result.retry_after_seconds, retry_after)
            self.assertNotIn("oauth-secret-token", repr(result))
            self.assertNotIn("private", repr(result))

    def test_client_has_no_mutating_public_method(self):
        public = {
            name for name in dir(BitrixOpenLinePreflightClient)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"close", "get_config", "get_dialog"})


class ControlledPilotPreviewTests(unittest.TestCase):
    def setUp(self):
        snapshot = OpenLineConfigSnapshot.model_validate(config_payload())
        self.preflight = OpenLinePreflightResult(
            status=OpenLinePreflightStatus.READY,
            reason="openline_snapshot_ready",
            chat_id=78733,
            dialog_id="chat78733",
            config=snapshot,
        )
        self.valid_from = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)
        self.valid_until = self.valid_from + timedelta(minutes=10)

    def test_builds_non_executable_link_and_exact_rollback(self):
        preview = build_controlled_pilot_preview(
            preflight=self.preflight,
            bot_id=300001,
            member_id="member-controlled",
            webhook_url="https://nia.example.com/bitrix-connector/webhook",
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        dumped = preview.model_dump(mode="json")

        self.assertFalse(dumped["registration"]["executable"])
        self.assertFalse(dumped["link"]["executable"])
        self.assertFalse(dumped["rollback"]["executable"])
        self.assertEqual(dumped["link"], {
            "method": "imopenlines.config.update",
            "executable": False,
            "payload": {"CONFIG_ID": 13, "PARAMS": {
                "WELCOME_BOT_ENABLE": "Y",
                "WELCOME_BOT_JOIN": "always",
                "WELCOME_BOT_ID": 300001,
                "WELCOME_BOT_TIME": 0,
                "WELCOME_BOT_LEFT": "close",
            }},
        })
        self.assertEqual(dumped["rollback"]["payload"], {
            "CONFIG_ID": 13,
            "PARAMS": {
                "WELCOME_BOT_ENABLE": "Y",
                "WELCOME_BOT_JOIN": "always",
                "WELCOME_BOT_ID": 245339,
                "WELCOME_BOT_TIME": 0,
                "WELCOME_BOT_LEFT": "close",
            },
        })
        self.assertEqual(dumped["allowlist"], {
            "member_id": "member-controlled",
            "bot_id": 300001,
            "dialog_id": "chat78733",
            "chat_id": 78733,
            "valid_from": "2026-07-27T02:00:00Z",
            "valid_until": "2026-07-27T02:10:00Z",
        })
        self.assertEqual(preview.impact_scope, "open_line_global")
        self.assertTrue(preview.requires_special_attention)

    def test_rejects_unready_snapshot_or_existing_bot(self):
        failed = self.preflight.model_copy(update={
            "status": OpenLinePreflightStatus.FAILED,
        })
        for preflight, bot_id, expected in (
            (failed, 300001, "openline_snapshot_not_ready"),
            (self.preflight, 245339, "openline_new_bot_id_invalid"),
            (self.preflight, 0, "openline_new_bot_id_invalid"),
        ):
            with self.assertRaisesRegex(ValueError, expected):
                build_controlled_pilot_preview(
                    preflight=preflight,
                    bot_id=bot_id,
                    member_id="member-controlled",
                    webhook_url="https://nia.example.com/bitrix-connector/webhook",
                    valid_from=self.valid_from,
                    valid_until=self.valid_until,
                )

    def test_requires_a_short_aware_window(self):
        cases = (
            (
                self.valid_from.replace(tzinfo=None),
                self.valid_until,
                "valid_from debe incluir zona horaria",
            ),
            (
                self.valid_from,
                self.valid_from + timedelta(minutes=16),
                "openline_pilot_window_invalid",
            ),
        )
        for valid_from, valid_until, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    build_controlled_pilot_preview(
                        preflight=self.preflight,
                        bot_id=300001,
                        member_id="member-controlled",
                        webhook_url="https://nia.example.com/bitrix-connector/webhook",
                        valid_from=valid_from,
                        valid_until=valid_until,
                    )


if __name__ == "__main__":
    unittest.main()
