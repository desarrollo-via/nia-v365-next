import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

from bitrix_connector.pilot_discovery_cli import (
    build_parser,
    execute_stored_oauth_discovery,
    main,
)


class PilotDiscoveryCliTests(unittest.TestCase):
    def test_parser_exposes_only_read_discovery_inputs(self):
        parser = build_parser()
        destinations = {
            action.dest
            for action in parser._actions
            if action.dest != "help"
        }

        self.assertEqual(
            destinations,
            {
                "deal_id",
                "timeout_seconds",
            },
        )

    def test_cli_uses_stored_oauth_and_prints_only_safe_result(self):
        safe_result = {
            "status": "found",
            "reason": "pilot_discovery_candidates_found",
            "candidates": [
                {
                    "chat_id": 1763,
                    "dialog_id": "chat1763",
                    "connector_id": "whatsapp",
                    "connector_title": "WhatsApp",
                    "crm_entity_type": "deal",
                    "crm_entity_id": 663001,
                    "pilot_rule": None,
                }
            ],
            "retry_after_seconds": 0,
        }
        output = io.StringIO()

        with patch(
            "bitrix_connector.pilot_discovery_cli."
            "execute_stored_oauth_discovery",
            new=AsyncMock(return_value=safe_result),
        ) as execute:
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--deal-id",
                        "663001",
                    ]
                )

        self.assertEqual(exit_code, 0)
        execute.assert_awaited_once_with(
            deal_id=663001,
            timeout_seconds=10.0,
        )
        self.assertIn('"dialog_id": "chat1763"', output.getvalue())
        self.assertNotIn("oauth-secret-token", output.getvalue())


class StoredOAuthDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_token_is_refreshed_once_and_resources_close(self):
        provider = unittest.mock.Mock()
        provider.get_access_token = AsyncMock(return_value="stale-secret")
        provider.refresh_access_token = AsyncMock(
            return_value="fresh-secret"
        )
        resources = unittest.mock.Mock(
            oauth_provider=provider,
            member_id="member-123",
            portal_url="https://portal.bitrix24.test",
        )
        resources.close = AsyncMock()
        factory = unittest.mock.Mock()
        factory.build = AsyncMock(return_value=resources)
        settings = unittest.mock.Mock()
        retry = {
            "status": "retry",
            "reason": "pilot_discovery_token_expired",
            "candidates": [],
            "retry_after_seconds": 0,
        }
        found = {
            "status": "found",
            "reason": "pilot_discovery_candidates_found",
            "candidates": [],
            "retry_after_seconds": 0,
        }

        with patch(
            "bitrix_connector.pilot_discovery_cli."
            "execute_read_only_discovery",
            new=AsyncMock(side_effect=[retry, found]),
        ) as execute:
            result = await execute_stored_oauth_discovery(
                deal_id=614949,
                settings=settings,
                factory=factory,
            )

        self.assertEqual(result, found)
        provider.get_access_token.assert_awaited_once_with("member-123")
        provider.refresh_access_token.assert_awaited_once_with(
            "member-123",
            "stale-secret",
        )
        self.assertEqual(execute.await_count, 2)
        self.assertEqual(
            [call.kwargs["access_token"] for call in execute.await_args_list],
            ["stale-secret", "fresh-secret"],
        )
        resources.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
