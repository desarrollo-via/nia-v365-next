import json
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from bitrix_connector.config import load_settings
from bitrix_connector.event_parser import parse_webhook_form
from bitrix_connector.g0_entrypoint import G0_WEBHOOK_PATH, create_g0_entrypoint
from bitrix_connector.openline_pilot_preflight import (
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    build_controlled_pilot_preview,
)
from bitrix_connector.pilot_scope import PilotScopePolicy


ORIGIN = "https://bot.example.com"
MEMBER_ID = "member-controlled"
APPLICATION_TOKEN = "application-secret"
CONTROLLED_BOT_ID = 300001


def line_snapshot() -> OpenLineConfigSnapshot:
    return OpenLineConfigSnapshot.model_validate(
        {
            "ID": 13,
            "LINE_NAME": "WhatApp Wazzup OFICIAL",
            "ACTIVE": "Y",
            "WELCOME_BOT_ENABLE": "Y",
            "WELCOME_BOT_JOIN": "always",
            "WELCOME_BOT_ID": 245339,
            "WELCOME_BOT_TIME": 0,
            "WELCOME_BOT_LEFT": "close",
            "NO_ANSWER_BOT_ID": 0,
            "CLOSE_BOT_ID": 0,
            "AUTO_CLOSE_BOT_ID": 0,
            "WORKTIME_DAYOFF_BOT_ID": 0,
        }
    )


def official_form(*, chat_id: int = 78733, dialog_id: str = "chat78733"):
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": str(CONTROLLED_BOT_ID),
        "data[message][id]": "9001",
        "data[message][chatId]": str(chat_id),
        "data[message][authorId]": "27",
        "data[message][text]": "NIA-R0-CONTROLADO",
        "data[chat][dialogId]": dialog_id,
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": MEMBER_ID,
        "auth[application_token]": APPLICATION_TOKEN,
        "auth[access_token]": "oauth-secret",
    }


class OpenLineR0RehearsalTests(unittest.IsolatedAsyncioTestCase):
    async def test_line_13_link_r0_off_and_exact_rollback(self):
        original = line_snapshot()
        preflight = OpenLinePreflightResult(
            status=OpenLinePreflightStatus.READY,
            reason="openline_snapshot_ready",
            chat_id=78733,
            dialog_id="chat78733",
            config=original,
        )
        start = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)
        preview = build_controlled_pilot_preview(
            preflight=preflight,
            bot_id=CONTROLLED_BOT_ID,
            member_id=MEMBER_ID,
            webhook_url=f"{ORIGIN}{G0_WEBHOOK_PATH}",
            valid_from=start,
            valid_until=start + timedelta(minutes=10),
        )

        original_bot = {
            "WELCOME_BOT_ENABLE": original.welcome_bot_enable,
            "WELCOME_BOT_JOIN": original.welcome_bot_join,
            "WELCOME_BOT_ID": original.welcome_bot_id,
            "WELCOME_BOT_TIME": original.welcome_bot_time,
            "WELCOME_BOT_LEFT": original.welcome_bot_left,
        }
        simulated_line = dict(original_bot)
        simulated_line.update(preview.link.payload.PARAMS.model_dump())
        self.assertEqual(simulated_line["WELCOME_BOT_ID"], CONTROLLED_BOT_ID)
        self.assertFalse(preview.link.executable)

        controlled_event = parse_webhook_form(official_form())
        policy = PilotScopePolicy(
            enabled=True,
            rules=(preview.allowlist,),
            emergency_stop=False,
            clock=lambda: start + timedelta(minutes=5),
        )
        self.assertEqual(
            policy.evaluate(controlled_event).model_dump(),
            {"accepted": True, "reason": "pilot_scope_allowed"},
        )
        other_event = parse_webhook_form(
            official_form(chat_id=78734, dialog_id="chat78734")
        )
        self.assertEqual(
            policy.evaluate(other_event).model_dump(),
            {"accepted": False, "reason": "outside_pilot_scope"},
        )

        settings = load_settings(
            {
                "NIA_BITRIX_MODE": "active",
                "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
                "NIA_BITRIX_MEMBER_ID": MEMBER_ID,
                "NIA_BITRIX_APPLICATION_TOKEN": APPLICATION_TOKEN,
            }
        )
        app = create_g0_entrypoint(
            public_origin=ORIGIN,
            settings_loader=lambda: settings,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
            response = await client.post(G0_WEBHOOK_PATH, data=official_form())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                key: response.json()[key]
                for key in (
                    "status",
                    "reason",
                    "effective_mode",
                    "identity_verified",
                    "persisted",
                    "nia_called",
                    "bitrix_written",
                )
            },
            {
                "status": "disabled",
                "reason": "connector_locked_off",
                "effective_mode": "off",
                "identity_verified": True,
                "persisted": False,
                "nia_called": False,
                "bitrix_written": False,
            },
        )
        self.assertNotIn(APPLICATION_TOKEN, response.text)
        self.assertNotIn("oauth-secret", response.text)

        simulated_line.update(preview.rollback.payload.PARAMS.model_dump())
        self.assertEqual(simulated_line, original_bot)
        self.assertEqual(
            json.dumps(simulated_line, sort_keys=True),
            json.dumps(original_bot, sort_keys=True),
        )
        self.assertFalse(preview.rollback.executable)


if __name__ == "__main__":
    unittest.main()
