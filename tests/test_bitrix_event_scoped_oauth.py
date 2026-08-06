import unittest

import httpx
from bitrix_connector.config import load_settings
from bitrix_connector.event_scoped_oauth import (
    BOT_EVENT_ACCESS_TOKEN_KEY,
    EventScopedOAuthOwner,
    event_scoped_oauth_is_documented_for_webhook_mode,
)
from bitrix_connector.g0_entrypoint import create_g0_entrypoint


def controlled_form():
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "ts": "1772093963",
        "data[bot][id]": "373259",
        "data[bot][code]": "nia_next_openline_controlled",
        BOT_EVENT_ACCESS_TOKEN_KEY: "event-oauth-private",
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
    }


class EventScopedOAuthOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_transfers_once_and_zeroizes_without_refresh_or_persistence(self):
        form = controlled_form()
        owner = EventScopedOAuthOwner.take_from_form_once(form)
        self.assertNotIn(BOT_EVENT_ACCESS_TOKEN_KEY, form)
        seen = []

        async def operation(view):
            seen.append(view.read_text())

        result = await owner.run_once(operation)
        self.assertEqual(result.state, "READY")
        self.assertEqual(result.token_transfer_calls, 1)
        self.assertEqual(result.token_view_reads, 1)
        self.assertEqual(result.refresh_calls, 0)
        self.assertEqual(result.persistence_calls, 0)
        self.assertTrue(result.resources_closed)
        self.assertTrue(result.token_buffer_zeroized)
        self.assertEqual(seen, ["event-oauth-private"])
        self.assertEqual((await owner.run_once(operation)).state, "NO-GO")

    async def test_failure_is_safe_and_reuse_is_rejected(self):
        owner = EventScopedOAuthOwner.take_from_form_once(controlled_form())

        async def operation(_view):
            raise RuntimeError("private detail")

        result = await owner.run_once(operation)
        self.assertEqual(result.state, "NO-GO")
        self.assertNotIn("private detail", repr(result))
        self.assertEqual((await owner.run_once(operation)).state, "NO-GO")

    def test_shape_audit_requires_bot_auth_and_top_level_identity(self):
        self.assertTrue(
            event_scoped_oauth_is_documented_for_webhook_mode(controlled_form())
        )
        form = controlled_form()
        form.pop("auth[application_token]")
        self.assertFalse(event_scoped_oauth_is_documented_for_webhook_mode(form))


class ProtectedWebhookOAuthObserverTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_inert_receipt_can_use_private_event_token_once(self):
        settings = load_settings(
            {
                "NIA_BITRIX_MODE": "off",
                "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
                "NIA_BITRIX_MEMBER_ID": "member-123",
                "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
            }
        )
        observed = []

        async def observer(event, receipt, received_settings, token_view):
            observed.append(
                (
                    event.bot_id,
                    event.chat_id,
                    receipt.reason,
                    received_settings.effective_mode.value,
                    token_view.read_text(),
                )
            )

        app = create_g0_entrypoint(
            public_origin="https://g0.example.test",
            settings_loader=lambda: settings,
            protected_oauth_observer=observer,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://g0.example.test"
        ) as client:
            response = await client.post(
                "/bitrix-connector/webhook", data=controlled_form()
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "connector_locked_off")
        self.assertEqual(
            observed,
            [(373259, 78733, "connector_locked_off", "off", "event-oauth-private")],
        )
        self.assertNotIn("event-oauth-private", response.text)

    async def test_invalid_identity_never_transfers_private_token(self):
        settings = load_settings(
            {
                "NIA_BITRIX_MODE": "off",
                "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
                "NIA_BITRIX_MEMBER_ID": "member-123",
                "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
            }
        )
        calls = 0

        async def observer(*_args):
            nonlocal calls
            calls += 1

        form = controlled_form()
        form["auth[application_token]"] = "attacker"
        app = create_g0_entrypoint(
            public_origin="https://g0.example.test",
            settings_loader=lambda: settings,
            protected_oauth_observer=observer,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://g0.example.test"
        ) as client:
            response = await client.post("/bitrix-connector/webhook", data=form)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "application_token_mismatch")
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
