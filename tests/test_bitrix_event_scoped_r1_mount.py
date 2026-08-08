import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.bitrix_event_scoped_r1_mount import (
    build_dormant_event_scoped_r1_mount,
)
from bitrix_connector.event_scoped_oauth import BOT_EVENT_ACCESS_TOKEN_KEY
import bitrix_connector.router as connector_router_module


def form():
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "373259",
        "data[bot][code]": "nia_next_openline_controlled",
        BOT_EVENT_ACCESS_TOKEN_KEY: "fixture-private-event-token",
        "data[message][id]": "9001",
        "data[message][chatId]": "78733",
        "data[message][authorId]": "27",
        "data[message][text]": "fixture controlled",
        "data[message][isSystem]": "0",
        "data[chat][dialogId]": "chat78733",
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "data[user][bot]": "0",
        "data[user][connector]": "1",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": "member-controlled",
        "auth[application_token]": "application-secret",
    }


class EventScopedR1MountTests(unittest.TestCase):
    def test_default_mount_is_dormant_and_has_no_activation_surface(self):
        mount = build_dormant_event_scoped_r1_mount()
        self.assertEqual(mount.state, "DORMANT")
        self.assertFalse(mount.requested)
        self.assertFalse(mount.enabled)
        self.assertIsNone(mount.observer)
        self.assertFalse(mount.activation_surface_available)
        self.assertEqual((mount.nia_calls, mount.bitrix_calls), (0, 0))

    def test_any_activation_attempt_fails_closed_without_observer(self):
        async def observer(*_args):
            raise AssertionError("must never be reachable")

        for kwargs in ({"requested": True}, {"observer": observer}):
            with self.subTest(kwargs=tuple(kwargs)):
                mount = build_dormant_event_scoped_r1_mount(**kwargs)
                self.assertEqual(mount.state, "UNAVAILABLE")
                self.assertFalse(mount.enabled)
                self.assertIsNone(mount.observer)
                self.assertFalse(mount.execution_enabled)

    def test_integrated_webhook_remains_inert_with_private_token_present(self):
        mount = build_dormant_event_scoped_r1_mount()
        app = FastAPI()
        app.include_router(connector_router_module.router)
        environ = {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-controlled",
            "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        }
        with patch.object(
            connector_router_module,
            "event_scoped_r1_mount",
            mount,
        ), patch.dict(os.environ, environ, clear=True):
            with TestClient(app) as client:
                response = client.post(
                    "/bitrix-connector/webhook",
                    data=form(),
                )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["reason"], "connector_locked_off")
        self.assertFalse(payload["persisted"])
        self.assertFalse(payload["nia_called"])
        self.assertFalse(payload["bitrix_written"])
        self.assertNotIn("fixture-private-event-token", response.text)


if __name__ == "__main__":
    unittest.main()
