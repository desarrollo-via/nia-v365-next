import asyncio
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_real_parser_adapter import (
    InjectedProtectedSessionParserAuthorization,
    PROTECTED_SESSION_REAL_CONFIRMATION,
    PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS,
    PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE,
    PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS,
    PROTECTED_SESSION_REAL_SOURCE,
    prepare_dormant_protected_session_real_parser,
)


ROOT = Path(__file__).resolve().parents[1]


def exact_kwargs():
    return {
        "confirm_code": PROTECTED_SESSION_REAL_CONFIRMATION,
        "protected_source": PROTECTED_SESSION_REAL_SOURCE,
        "preflight_timeout_seconds": PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS,
        "confirmation_timeout_seconds": (
            PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS
        ),
    }


class ProtectedSessionRealParserAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_is_dormant_and_never_reads_authorization(self):
        calls = 0

        async def authorization_reader():
            nonlocal calls
            calls += 1
            raise AssertionError("authorization must not run")

        result = await prepare_dormant_protected_session_real_parser(
            **exact_kwargs(), authorization_reader=authorization_reader
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.reason, "protected_history_session_real_parser_dormant_default")
        self.assertTrue(result.exact_contract_valid)
        self.assertEqual(calls, 0)

    async def test_exact_injected_authorization_prepares_contract_only(self):
        calls = 0

        async def authorization_reader():
            nonlocal calls
            calls += 1
            return InjectedProtectedSessionParserAuthorization(
                approved=True,
                scope=PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE,
            )

        result = await prepare_dormant_protected_session_real_parser(
            **exact_kwargs(),
            activation_requested=True,
            authorization_reader=authorization_reader,
        )
        self.assertEqual(result.state, "PREPARED")
        self.assertEqual(calls, 1)
        self.assertTrue(result.parser_contract_prepared)
        self.assertFalse(result.parser_real_enabled)
        self.assertFalse(result.command_available)
        self.assertEqual(result.builder_calls, 0)
        self.assertEqual(result.source_calls, 0)
        self.assertEqual(result.external_calls, 0)

    async def test_divergent_contract_stops_before_authorization(self):
        calls = 0

        async def authorization_reader():
            nonlocal calls
            calls += 1
            raise AssertionError("authorization must not run")

        values = exact_kwargs()
        values["confirmation_timeout_seconds"] = 301.0
        result = await prepare_dormant_protected_session_real_parser(
            **values,
            activation_requested=True,
            authorization_reader=authorization_reader,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertFalse(result.exact_contract_valid)
        self.assertEqual(calls, 0)

    async def test_rejected_authorization_fails_closed(self):
        async def authorization_reader():
            return InjectedProtectedSessionParserAuthorization(
                approved=False,
                scope=PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE,
            )

        result = await prepare_dormant_protected_session_real_parser(
            **exact_kwargs(),
            activation_requested=True,
            authorization_reader=authorization_reader,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.authorization_calls, 1)
        self.assertFalse(result.authorization_verified)

    async def test_cancellation_is_normalized_without_authority(self):
        async def authorization_reader():
            raise asyncio.CancelledError

        result = await prepare_dormant_protected_session_real_parser(
            **exact_kwargs(),
            activation_requested=True,
            authorization_reader=authorization_reader,
        )
        self.assertEqual(result.state, "CANCELLED")
        self.assertFalse(result.parser_real_enabled)
        self.assertFalse(result.real_execution_authorized)

    async def test_snapshot_contains_no_real_authority_or_values(self):
        result = await prepare_dormant_protected_session_real_parser(
            **exact_kwargs()
        )
        serialized = repr(asdict(result))
        for forbidden in ("mongodb://", "Bearer ", "client-secret-value", ".env"):
            self.assertNotIn(forbidden, serialized)
        self.assertFalse(result.message_request_authorized)

    def test_source_has_no_parser_source_builder_or_external_surface(self):
        source = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_session_real_parser_adapter.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "argparse", "open(", "Path(", "os.environ", "load_dotenv",
            "AllowlistedDotenvSource", "session_builder", "get_access_token",
            "refresh_access_token", "get_dialog(", "get_session_history(",
            "httpx", "pymongo", "subprocess", "socket", "input(",
            "asyncio.run", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
