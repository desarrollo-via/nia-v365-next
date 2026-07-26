import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, Mock, patch

from bitrix_connector.bot_v2_preflight import (
    BotV2PreflightResult,
    BotV2PreflightStatus,
)
from bitrix_connector.bot_v2_preflight_cli import (
    build_parser,
    execute_stored_oauth_preflight,
    main,
)


class BotV2PreflightCliTests(unittest.TestCase):
    def test_parser_exposes_only_timeout(self):
        destinations = {
            action.dest
            for action in build_parser()._actions
            if action.dest != "help"
        }
        self.assertEqual(destinations, {"timeout_seconds"})

    def test_main_prints_safe_result_without_registration_inputs(self):
        result = BotV2PreflightResult(
            status=BotV2PreflightStatus.READY,
            reason="bot_v2_preflight_no_existing_bot",
            rest_revision=33,
            registration_needed=True,
        )
        output = io.StringIO()
        with patch(
            "bitrix_connector.bot_v2_preflight_cli."
            "execute_stored_oauth_preflight",
            new=AsyncMock(return_value=result),
        ):
            with redirect_stdout(output):
                exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "ready"', output.getvalue())
        self.assertNotIn("access_token", output.getvalue())
        self.assertNotIn("register", output.getvalue())


class StoredOAuthBotV2PreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_token_refreshes_once_and_closes_resources(self):
        provider = Mock()
        provider.get_access_token = AsyncMock(return_value="stale-secret")
        provider.refresh_access_token = AsyncMock(
            return_value="fresh-secret"
        )
        resources = Mock(
            oauth_provider=provider,
            member_id="member-123",
            portal_url="https://portal.bitrix24.test",
        )
        resources.close = AsyncMock()
        factory = Mock()
        factory.build = AsyncMock(return_value=resources)
        execute_once = AsyncMock(
            side_effect=[
                BotV2PreflightResult(
                    status=BotV2PreflightStatus.RETRY,
                    reason="bot_v2_preflight_token_expired",
                ),
                BotV2PreflightResult(
                    status=BotV2PreflightStatus.READY,
                    reason="bot_v2_preflight_no_existing_bot",
                    rest_revision=33,
                    registration_needed=True,
                ),
            ]
        )

        result = await execute_stored_oauth_preflight(
            settings=Mock(),
            resources_factory=factory,
            execute_once=execute_once,
        )

        self.assertEqual(result.status, BotV2PreflightStatus.READY)
        provider.get_access_token.assert_awaited_once_with("member-123")
        provider.refresh_access_token.assert_awaited_once_with(
            "member-123",
            "stale-secret",
        )
        self.assertEqual(
            [call.kwargs["access_token"] for call in execute_once.await_args_list],
            ["stale-secret", "fresh-secret"],
        )
        resources.close.assert_awaited_once()

    async def test_non_expiration_retry_does_not_refresh(self):
        provider = Mock()
        provider.get_access_token = AsyncMock(return_value="oauth-secret")
        provider.refresh_access_token = AsyncMock()
        resources = Mock(
            oauth_provider=provider,
            member_id="member-123",
            portal_url="https://portal.bitrix24.test",
        )
        resources.close = AsyncMock()
        factory = Mock()
        factory.build = AsyncMock(return_value=resources)
        execute_once = AsyncMock(
            return_value=BotV2PreflightResult(
                status=BotV2PreflightStatus.RETRY,
                reason="bot_v2_preflight_retryable",
            )
        )

        result = await execute_stored_oauth_preflight(
            settings=Mock(),
            resources_factory=factory,
            execute_once=execute_once,
        )

        self.assertEqual(result.status, BotV2PreflightStatus.RETRY)
        provider.refresh_access_token.assert_not_awaited()
        execute_once.assert_awaited_once()
        resources.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
