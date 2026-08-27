from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.event_parser import parse_webhook_form
from bitrix_connector.h1_visible import (
    H1_BOT_ID,
    H1_CHAT_ID,
    H1_TTL_SECONDS,
    H1VisibleBuffer,
    create_h1_visible_router,
)
from bitrix_connector.models import WebhookEventSummary, WebhookReceipt


class H1VisibleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 27, 15, tzinfo=timezone.utc)
        self.buffer = H1VisibleBuffer(clock=lambda: self.now)

    async def test_exact_event_is_shared_by_html_and_json_and_expires(self):
        event = parse_webhook_form({
            "event": "ONIMBOTV2MESSAGEADD", "ts": "1787833200",
            "data[bot][id]": str(H1_BOT_ID), "data[message][id]": "900001",
            "data[message][chatId]": str(H1_CHAT_ID), "data[message][authorId]": "99",
            "data[message][text]": "H1 <visible> & seguro", "data[message][isSystem]": "0",
            "data[chat][dialogId]": "chat78733", "data[user][id]": "99",
            "data[user][bot]": "0", "data[user][connector]": "0",
            "auth[domain]": "example.bitrix24.es", "auth[member_id]": "fixture-member",
        })
        receipt = WebhookReceipt(
            status="disabled", reason="connector_locked_off", effective_mode="off",
            event_key="a" * 64, identity_verified=True, redacted_secret_fields=0,
            duplicate_detection="not_persisted", persisted=False, nia_called=False,
            bitrix_written=False, event_summary=WebhookEventSummary(
                event=event.event, bot_id=event.bot_id, message_id=event.message_id,
                chat_id=event.chat_id, dialog_id=event.dialog_id,
                text_length=len(event.text), is_system=event.is_system,
            ),
        )
        app = FastAPI()
        app.include_router(create_h1_visible_router(self.buffer), prefix="/bitrix-connector")
        with TestClient(app) as client:
            empty_response = client.get("/bitrix-connector/h1-visible.json")
        self.assertEqual(empty_response.json()["status"], "empty")
        await self.buffer.observe(event, receipt, None)  # type: ignore[arg-type]
        with TestClient(app) as client:
            json_response = client.get("/bitrix-connector/h1-visible.json")
            html_response = client.get("/bitrix-connector/h1-visible")
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["record"]["event_key"], receipt.event_key)
        self.assertIn("H1 &lt;visible&gt; &amp; seguro", html_response.text)
        self.assertEqual(json_response.headers["cache-control"], "no-store")
        self.now += timedelta(seconds=H1_TTL_SECONDS)
        self.assertIsNone(self.buffer.snapshot())

    async def test_wrong_scope_and_effectful_receipt_are_ignored(self):
        event = parse_webhook_form({
            "event": "ONIMBOTV2MESSAGEADD", "data[bot][id]": str(H1_BOT_ID),
            "data[message][id]": "1", "data[message][chatId]": "78734",
            "data[message][authorId]": "99", "data[chat][dialogId]": "chat78734",
            "data[message][isSystem]": "0", "data[user][id]": "99",
            "data[user][bot]": "0", "data[user][connector]": "0",
            "auth[domain]": "example.bitrix24.es", "auth[member_id]": "fixture-member",
        })
        receipt = WebhookReceipt(
            status="disabled", reason="connector_locked_off", effective_mode="off",
            event_key="a" * 64, identity_verified=True, redacted_secret_fields=0,
            duplicate_detection="not_persisted", persisted=False, nia_called=False,
            bitrix_written=False, event_summary=WebhookEventSummary(
                event=event.event, bot_id=event.bot_id, message_id=event.message_id,
                chat_id=event.chat_id, dialog_id=event.dialog_id,
                text_length=len(event.text), is_system=event.is_system,
            ),
        )
        await self.buffer.observe(event, receipt, None)  # type: ignore[arg-type]
        self.assertIsNone(self.buffer.snapshot())


if __name__ == "__main__":
    unittest.main()
