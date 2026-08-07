import unittest
from dataclasses import asdict, replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_command_readiness_closure import (
    ProtectedSessionCommandReadinessClosureSnapshot,
    close_static_protected_session_command_readiness,
)
from bitrix_connector.bitrix_history_r0_protected_session_final_composition_audit import (
    PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT,
)


ROOT = Path(__file__).resolve().parents[1]


class ProtectedSessionCommandReadinessClosureTests(unittest.TestCase):
    def test_exact_m30_contract_closes_static_readiness(self):
        result = close_static_protected_session_command_readiness()

        self.assertEqual(result.phase, "M31")
        self.assertEqual(result.state, "READY-AWAITING-AUTHORIZATION")
        self.assertEqual(
            result.reason, "protected_history_session_command_available_static_only"
        )
        self.assertTrue(result.m30_contract_consumed)
        self.assertTrue(result.technical_readiness_closed)
        self.assertTrue(result.owner_complete)
        self.assertTrue(result.command_available)

    def test_available_indicator_does_not_make_owner_invocable(self):
        result = close_static_protected_session_command_readiness()

        self.assertTrue(result.command_indicator_static_only)
        self.assertFalse(result.owner_module_invocable)
        self.assertFalse(result.command_invocation_authorized)
        self.assertFalse(callable(result))
        self.assertFalse(hasattr(result, "execute"))

    def test_all_operational_counts_remain_zero(self):
        result = close_static_protected_session_command_readiness()

        for field in (
            "parser_calls", "builder_calls", "source_calls", "materializer_calls",
            "confirmation_calls", "command_calls", "external_calls",
        ):
            self.assertEqual(getattr(result, field), 0, field)

    def test_all_external_authorities_remain_false(self):
        result = close_static_protected_session_command_readiness()

        for field in (
            "source_open_authorized", "oauth_read_authorized",
            "bitrix_read_authorized", "real_execution_authorized",
            "message_request_authorized",
        ):
            self.assertFalse(getattr(result, field), field)

    def test_degraded_m30_contract_is_rejected(self):
        degraded = replace(
            PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT,
            real_execution_authorized=True,
        )
        result = close_static_protected_session_command_readiness(
            audit_contract=degraded
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertFalse(result.command_available)
        self.assertFalse(result.m30_contract_consumed)

    def test_wrong_dependency_type_is_rejected_and_redacted(self):
        result = close_static_protected_session_command_readiness(
            audit_contract=object()
        )
        payload = asdict(result)

        self.assertEqual(result.state, "NO-GO")
        self.assertNotIn("mongodb://", repr(payload))
        self.assertNotIn("Bearer ", repr(payload))
        self.assertNotIn(".env", repr(payload))

    def test_source_has_no_command_secret_external_or_interactive_surface(self):
        source = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_session_command_readiness_closure.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "Path(", "open(", ".env", "load_dotenv", "os.environ",
            "AllowlistedDotenvSource", "get_access_token", "refresh_access_token",
            "get_dialog(", "get_session_history(", "httpx", "pymongo",
            "subprocess", "socket", "argparse", "input(", "asyncio.run",
            "Invoke-RestMethod", "parse_args(", "main(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
