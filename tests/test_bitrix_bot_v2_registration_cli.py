import unittest
from unittest.mock import AsyncMock, Mock

from bitrix_connector.bot_v2_preflight import (
    BotV2PreflightResult,
    BotV2PreflightStatus,
)
from bitrix_connector.bot_v2_registration import (
    ControlledRegistrationResult,
    ControlledRegistrationStatus,
)
from bitrix_connector.bot_v2_registration_cli import (
    A4Status,
    build_parser,
    execute_stored_oauth_registration,
)
from bitrix_connector.config import load_settings
from bitrix_connector.openline_pilot_preflight import (
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
)


def settings():
    return load_settings({})


def ready_bot():
    return BotV2PreflightResult(
        status=BotV2PreflightStatus.READY,
        reason="bot_v2_preflight_no_existing_bot",
        rest_revision=35,
        registration_needed=True,
    )


def existing_bot(bot_id=300001):
    return BotV2PreflightResult(
        status=BotV2PreflightStatus.EXISTING_COMPATIBLE,
        reason="bot_v2_preflight_existing_compatible",
        rest_revision=35,
        existing_bot_id=bot_id,
    )


def original_line(bot_id=245339):
    snapshot = OpenLineConfigSnapshot.model_validate({
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
    })
    return OpenLinePreflightResult(
        status=OpenLinePreflightStatus.READY,
        reason="openline_snapshot_ready",
        chat_id=78733,
        dialog_id="chat78733",
        config=snapshot,
    )


def resources_factory():
    provider = Mock()
    provider.get_access_token = AsyncMock(return_value="oauth-secret")
    provider.refresh_access_token = AsyncMock(return_value="fresh-secret")
    resources = Mock(
        oauth_provider=provider,
        member_id="member-123",
        portal_url="https://portal.bitrix24.test",
    )
    resources.close = AsyncMock()
    factory = Mock()
    factory.build = AsyncMock(return_value=resources)
    return factory, resources


class A4RegistrationCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_registers_once_verifies_bot_and_preserves_line(self):
        factory, resources = resources_factory()
        bot_preflight = AsyncMock(side_effect=[ready_bot(), existing_bot()])
        line_preflight = AsyncMock(
            side_effect=[original_line(), original_line()]
        )
        registration = AsyncMock(return_value=ControlledRegistrationResult(
            status=ControlledRegistrationStatus.REGISTERED,
            reason="bot_v2_registration_created",
            bot_id=300001,
            registration_attempted=True,
        ))

        result = await execute_stored_oauth_registration(
            settings=settings(),
            resources_factory=factory,
            bot_preflight_once=bot_preflight,
            line_preflight_once=line_preflight,
            registration_once=registration,
        )

        self.assertEqual(result.status, A4Status.REGISTERED)
        self.assertEqual(result.bot_id, 300001)
        self.assertTrue(result.registration_verified)
        self.assertTrue(result.line_unchanged)
        registration.assert_awaited_once()
        self.assertEqual(bot_preflight.await_count, 2)
        self.assertEqual(line_preflight.await_count, 2)
        resources.close.assert_awaited_once()
        self.assertNotIn("oauth-secret", repr(result))

    async def test_existing_compatible_is_idempotent(self):
        factory, resources = resources_factory()
        bot_preflight = AsyncMock(
            side_effect=[existing_bot(), existing_bot()]
        )
        registration = AsyncMock(return_value=ControlledRegistrationResult(
            status=ControlledRegistrationStatus.IDEMPOTENT,
            reason="bot_v2_registration_existing_compatible",
            bot_id=300001,
        ))

        result = await execute_stored_oauth_registration(
            settings=settings(),
            resources_factory=factory,
            bot_preflight_once=bot_preflight,
            line_preflight_once=AsyncMock(
                side_effect=[original_line(), original_line()]
            ),
            registration_once=registration,
        )

        self.assertEqual(result.status, A4Status.IDEMPOTENT)
        self.assertFalse(result.registration_attempted)
        resources.close.assert_awaited_once()

    async def test_changed_line_stops_before_registration(self):
        factory, resources = resources_factory()
        registration = AsyncMock()

        result = await execute_stored_oauth_registration(
            settings=settings(),
            resources_factory=factory,
            bot_preflight_once=AsyncMock(return_value=ready_bot()),
            line_preflight_once=AsyncMock(
                return_value=original_line(bot_id=999999)
            ),
            registration_once=registration,
        )

        self.assertEqual(result.status, A4Status.FAILED)
        self.assertEqual(result.reason, "a4_line_snapshot_not_original")
        registration.assert_not_awaited()
        resources.close.assert_awaited_once()

    async def test_failed_postcheck_reports_created_bot_without_rollback(self):
        factory, resources = resources_factory()
        result = await execute_stored_oauth_registration(
            settings=settings(),
            resources_factory=factory,
            bot_preflight_once=AsyncMock(
                side_effect=[ready_bot(), ready_bot()]
            ),
            line_preflight_once=AsyncMock(
                side_effect=[original_line(), original_line()]
            ),
            registration_once=AsyncMock(return_value=ControlledRegistrationResult(
                status=ControlledRegistrationStatus.REGISTERED,
                reason="bot_v2_registration_created",
                bot_id=300001,
                registration_attempted=True,
            )),
        )

        self.assertEqual(result.status, A4Status.FAILED)
        self.assertEqual(result.bot_id, 300001)
        self.assertTrue(result.registration_attempted)
        self.assertFalse(result.registration_verified)
        resources.close.assert_awaited_once()

    def test_cli_requires_exact_controlled_code(self):
        parser = build_parser()
        parsed = parser.parse_args([
            "--confirm-code",
            "nia_next_openline_controlled",
        ])
        self.assertEqual(parsed.confirm_code, "nia_next_openline_controlled")
        destinations = {
            action.dest for action in parser._actions if action.dest != "help"
        }
        self.assertEqual(destinations, {"confirm_code", "timeout_seconds"})


if __name__ == "__main__":
    unittest.main()
