import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from bitrix_connector.bitrix_history_r0_protected_session_plan_launcher import (
    preview_real_ready_protected_history_session_plan_launcher,
)
from bitrix_connector.bitrix_history_r0_protected_session_readiness_contract import (
    FUTURE_PROTECTED_SESSION_AUTHORIZATION,
    FUTURE_PROTECTED_SESSION_OWNER_COMMAND,
    FUTURE_PROTECTED_SESSION_OWNER_MODULE,
    PROTECTED_HISTORY_SESSION_READINESS_CONTRACT,
)


ROOT = Path(__file__).resolve().parents[1]


class ProtectedSessionReadinessContractTests(unittest.TestCase):
    def test_m33_selects_invocable_preflight_owner_but_awaits_new_authorization(self):
        contract = PROTECTED_HISTORY_SESSION_READINESS_CONTRACT

        self.assertEqual(contract.phase, "M33")
        self.assertEqual(contract.state, "READY-AWAITING-AUTHORIZATION")
        self.assertEqual(
            contract.reason,
            "protected_preflight_failure_category_awaiting_new_authorization",
        )
        self.assertTrue(contract.m31_static_readiness_consumed)
        self.assertTrue(contract.m32_authorization_consumed)
        self.assertTrue(contract.m19_launcher_bound)
        self.assertTrue(contract.m20_materializer_bound)
        self.assertTrue(contract.m21_gate_owner_bound)
        self.assertTrue(contract.m22_human_boundary_bound)
        self.assertTrue(contract.chain_complete_in_doubles)
        self.assertTrue(contract.owner_module_present)
        self.assertTrue(contract.fixture_command_available)
        self.assertTrue(contract.real_ready_composition_bound)
        self.assertTrue(contract.activation_delta_frozen)
        self.assertTrue(contract.dormant_real_parser_adapter_bound)
        self.assertTrue(contract.parser_contract_prepared_in_doubles)
        self.assertFalse(contract.parser_real_enabled)
        self.assertTrue(contract.dormant_builder_composition_bound)
        self.assertTrue(contract.builder_contract_prepared_in_doubles)
        self.assertTrue(contract.path_builder_bound)
        self.assertTrue(contract.source_builder_bound)
        self.assertTrue(contract.private_builder_bound)
        self.assertFalse(contract.builder_real_enabled)
        self.assertTrue(contract.outer_confirmation_composition_bound)
        self.assertTrue(contract.outer_confirmation_prepared_in_doubles)
        self.assertFalse(contract.outer_confirmation_default_enabled)
        self.assertEqual(contract.outer_confirmation_attempt_limit, 1)
        self.assertEqual(contract.outer_confirmation_timeout_seconds, 300)
        self.assertTrue(contract.final_composition_audit_verified)
        self.assertTrue(contract.rejection_terminal_verified)
        self.assertTrue(contract.timeout_terminal_verified)
        self.assertTrue(contract.cancellation_terminal_verified)
        self.assertTrue(contract.cleanup_verified_in_doubles)
        self.assertTrue(contract.technical_readiness_closed)
        self.assertTrue(contract.owner_complete)
        self.assertTrue(contract.command_available)
        self.assertFalse(contract.command_indicator_static_only)
        self.assertTrue(contract.owner_module_invocable)
        self.assertFalse(contract.command_invocation_authorized)
        self.assertTrue(contract.authorization_request_ready)
        self.assertTrue(contract.selected_preflight_owner)
        self.assertTrue(contract.session_fixture_cli_preserved)
        self.assertTrue(contract.failure_category_allowlist_bound)
        self.assertIn("dialog_identity_mismatch", contract.failure_category_allowlist)
        self.assertIn("oauth_token_expired", contract.failure_category_allowlist)
        self.assertTrue(contract.repeat_authorization_required)
        self.assertTrue(contract.authorization_ready_for_use)
        self.assertFalse(contract.real_execution_authorized)
        self.assertFalse(contract.message_request_authorized)

    def test_source_is_frozen_by_name_and_allowlist_without_opening(self):
        contract = PROTECTED_HISTORY_SESSION_READINESS_CONTRACT
        preview = preview_real_ready_protected_history_session_plan_launcher()

        self.assertEqual(contract.source_kind, "local-dotenv-allowlisted-one-shot")
        self.assertEqual(contract.source_path, ".env")
        self.assertEqual(contract.protected_name_allowlist, PROTECTED_SETTING_NAMES)
        self.assertFalse(contract.source_open_authorized)
        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(preview.source_calls, 0)
        self.assertEqual(preview.external_calls, 0)

    def test_preflight_owner_is_invocable_but_invocation_is_unauthorized(self):
        contract = PROTECTED_HISTORY_SESSION_READINESS_CONTRACT
        expected_path = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_preflight_execution_owner.py"
        )

        self.assertEqual(contract.owner_module, FUTURE_PROTECTED_SESSION_OWNER_MODULE)
        self.assertEqual(contract.owner_command, FUTURE_PROTECTED_SESSION_OWNER_COMMAND)
        self.assertTrue(expected_path.exists())
        self.assertTrue(contract.command_available)
        self.assertFalse(contract.command_indicator_static_only)
        self.assertTrue(contract.owner_module_invocable)
        self.assertFalse(contract.command_invocation_authorized)
        self.assertIn("protected_preflight_execution_owner", contract.owner_command)
        self.assertNotIn("protected_session_cli", contract.owner_command)

    def test_existing_clis_are_not_m19_m22_chain_owner(self):
        handoff_source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_handoff_cli.py"
        ).read_text(encoding="utf-8")
        helper_source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_protected_helper_cli.py"
        ).read_text(encoding="utf-8")
        required_imports = (
            "protected_session_plan_launcher",
            "protected_session_plan_materializer",
            "protected_session_gate_owner",
            "protected_session_human_boundary_contract",
        )

        for required in required_imports:
            self.assertNotIn(required, handoff_source)
            self.assertNotIn(required, helper_source)
        self.assertFalse(PROTECTED_HISTORY_SESSION_READINESS_CONTRACT.legacy_handoff_cli_is_owner)
        self.assertFalse(PROTECTED_HISTORY_SESSION_READINESS_CONTRACT.fixture_helper_cli_is_owner)

    def test_future_authorization_is_exact_conditioned_and_read_only(self):
        authorization = FUTURE_PROTECTED_SESSION_AUTHORIZATION

        self.assertIn("owner M33", authorization)
        self.assertIn("command_available=true", authorization)
        self.assertIn("owner_module_invocable=true", authorization)
        self.assertIn("autorización M32 anterior permanece consumida", authorization)
        self.assertIn("failure_category", authorization)
        self.assertIn("AllowlistedDotenvSource", authorization)
        for name in PROTECTED_SETTING_NAMES:
            self.assertIn(name, authorization)
        self.assertIn("imopenlines.dialog.get", authorization)
        self.assertIn("chat78733", authorization)
        self.assertIn("No autorizo lectura de historial", authorization)
        self.assertIn("no existe rollback externo", authorization)

    def test_contract_contains_no_value_or_real_authority(self):
        serialized = repr(asdict(PROTECTED_HISTORY_SESSION_READINESS_CONTRACT))

        for private_value in (
            "fictional-value", "mongodb://", "Bearer ", "client-secret-value",
        ):
            self.assertNotIn(private_value, serialized)
        self.assertFalse(PROTECTED_HISTORY_SESSION_READINESS_CONTRACT.source_open_authorized)
        self.assertFalse(PROTECTED_HISTORY_SESSION_READINESS_CONTRACT.real_execution_authorized)

    def test_readiness_source_has_no_external_or_interactive_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_readiness_contract.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "os.environ", "load_dotenv", "get_access_token",
            "refresh_access_token", "get_dialog(", "get_session_history(",
            "httpx", "pymongo", "subprocess", "socket", "argparse", "input(",
            "asyncio.run", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
