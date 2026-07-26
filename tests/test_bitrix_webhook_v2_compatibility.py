import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from bitrix_connector.config import load_settings
from bitrix_connector.router import router


class BitrixWebhookV2CompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_route_accepts_official_v2_form_shape_and_stays_inert(self):
        app = FastAPI()
        app.include_router(router)
        settings = load_settings(
            {
                "NIA_BITRIX_MODE": "off",
                "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
                "NIA_BITRIX_MEMBER_ID": "member-123",
                "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
            }
        )
        form = {
            "event": "ONIMBOTV2MESSAGEADD",
            "ts": "1772093963",
            "data[bot][id]": "456",
            "data[bot][code]": "nia_next_openline_controlled",
            "data[bot][auth][access_token]": "nested-oauth-secret",
            "data[message][id]": "9001",
            "data[message][uuid]": "message-uuid",
            "data[message][chatId]": "78733",
            "data[message][authorId]": "27",
            "data[message][text]": "mensaje controlado",
            "data[message][isSystem]": "0",
            "data[chat][dialogId]": "chat78733",
            "data[chat][type]": "openChannel",
            "data[chat][entityType]": "LINES",
            "data[user][id]": "27",
            "data[user][bot]": "0",
            "data[user][connector]": "1",
            "auth[domain]": "portal.bitrix24.test",
            "auth[member_id]": "member-123",
            "auth[application_token]": "application-secret",
            "auth[access_token]": "top-level-oauth-secret",
        }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch("bitrix_connector.router.load_settings", return_value=settings):
                response = await client.post(
                    "/bitrix-connector/webhook",
                    data=form,
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "disabled")
        self.assertEqual(payload["reason"], "connector_locked_off")
        self.assertTrue(payload["identity_verified"])
        self.assertEqual(payload["effective_mode"], "off")
        self.assertFalse(payload["persisted"])
        self.assertFalse(payload["nia_called"])
        self.assertFalse(payload["bitrix_written"])
        self.assertEqual(payload["event_summary"]["bot_id"], 456)
        self.assertEqual(payload["event_summary"]["chat_id"], 78733)
        self.assertEqual(payload["event_summary"]["dialog_id"], "chat78733")
        serialized = response.text
        self.assertNotIn("application-secret", serialized)
        self.assertNotIn("nested-oauth-secret", serialized)
        self.assertNotIn("top-level-oauth-secret", serialized)


if __name__ == "__main__":
    unittest.main()
