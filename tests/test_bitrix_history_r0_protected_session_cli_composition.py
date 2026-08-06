import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_cli_composition import (
    PROTECTED_SESSION_REAL_SOURCE_NAME,
    PreparedProtectedHistorySessionOwnerComposition,
    compose_real_ready_protected_session_owner,
    fail_closed_outer_confirmation_reader,
    preview_real_ready_protected_session_owner,
)
from bitrix_connector.bitrix_history_r0_protected_session_plan_launcher import (
    fail_closed_inner_confirmation_reader,
)
from bitrix_connector.bitrix_history_r0_protected_session_readiness_contract import (
    PROTECTED_HISTORY_SESSION_READINESS_CONTRACT,
)


ROOT = Path(__file__).resolve().parents[1]


class ProtectedSessionCliCompositionTests(unittest.IsolatedAsyncioTestCase):
    def test_real_ready_preview_binds_all_and_keeps_every_counter_zero(self):
        preview = preview_real_ready_protected_session_owner()

        self.assertEqual(preview.state, "PREPARED")
        for field in (
            "source_name_bound", "path_builder_bound", "source_builder_bound",
            "plan_launcher_bound", "materializer_bound", "inner_confirmation_bound",
            "outer_confirmation_bound", "gate_owner_bound", "cli_owner_bound",
        ):
            self.assertTrue(getattr(preview, field), field)
        for field in (
            "source_select_calls", "path_calls", "source_calls",
            "plan_launcher_calls", "materializer_calls", "inner_confirmation_calls",
            "outer_confirmation_calls", "gate_owner_calls", "cli_owner_calls",
            "external_calls",
        ):
            self.assertEqual(getattr(preview, field), 0, field)
        self.assertTrue(preview.real_parser_blocked)
        self.assertFalse(preview.command_available)

    def test_preview_never_invokes_injected_dependencies(self):
        calls = {name: 0 for name in (
            "path", "source", "launcher", "materializer", "inner", "outer",
            "gate", "cli",
        )}

        def spy(name):
            def dependency(*_args, **_kwargs):
                calls[name] += 1
                raise AssertionError(f"{name} must not run")
            return dependency

        preview = preview_real_ready_protected_session_owner(
            compose_owner=lambda: compose_real_ready_protected_session_owner(
                path_builder=spy("path"), source_builder=spy("source"),
                plan_launcher=spy("launcher"), materializer=spy("materializer"),
                inner_confirmation_reader=spy("inner"),
                outer_confirmation_reader=spy("outer"), gate_owner=spy("gate"),
                cli_owner=spy("cli"),
            )
        )
        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(calls, {name: 0 for name in calls})

    def test_composed_owner_is_redacted_and_not_invocable(self):
        owner = compose_real_ready_protected_session_owner()

        self.assertIs(type(owner), PreparedProtectedHistorySessionOwnerComposition)
        self.assertEqual(
            repr(owner),
            "PreparedProtectedHistorySessionOwnerComposition(<redacted>)",
        )
        self.assertFalse(callable(owner))
        self.assertFalse(hasattr(owner, "execute"))

    async def test_both_real_confirmation_references_fail_closed(self):
        with self.assertRaises(RuntimeError):
            await fail_closed_inner_confirmation_reader()
        with self.assertRaises(RuntimeError):
            await fail_closed_outer_confirmation_reader()

    def test_invalid_source_or_dependency_fails_closed_in_preview(self):
        invalid_source = preview_real_ready_protected_session_owner(
            compose_owner=lambda: compose_real_ready_protected_session_owner(
                source_name="fixture"
            )
        )
        invalid_dependency = preview_real_ready_protected_session_owner(
            compose_owner=lambda: compose_real_ready_protected_session_owner(
                materializer=None
            )
        )

        self.assertEqual(invalid_source.state, "NO-GO")
        self.assertEqual(invalid_dependency.state, "NO-GO")

    def test_m33_selects_preflight_owner_and_real_invocation_is_unauthorized(self):
        contract = PROTECTED_HISTORY_SESSION_READINESS_CONTRACT

        self.assertEqual(contract.phase, "M33")
        self.assertEqual(
            contract.reason,
            "protected_preflight_failure_category_awaiting_new_authorization",
        )
        self.assertTrue(contract.real_ready_composition_bound)
        self.assertTrue(contract.command_available)
        self.assertFalse(contract.command_indicator_static_only)
        self.assertTrue(contract.owner_module_invocable)
        self.assertTrue(contract.session_fixture_cli_preserved)
        self.assertTrue(contract.failure_category_allowlist_bound)
        self.assertTrue(contract.repeat_authorization_required)
        self.assertFalse(contract.command_invocation_authorized)
        self.assertFalse(contract.source_open_authorized)
        self.assertFalse(contract.real_execution_authorized)

    def test_source_has_no_invocation_or_external_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_cli_composition.py"
        ).read_text(encoding="utf-8")
        self.assertIn(PROTECTED_SESSION_REAL_SOURCE_NAME, source)
        for forbidden in (
            ".open(", "os.environ", "load_dotenv", "get_access_token",
            "refresh_access_token", "get_dialog(", "get_session_history(",
            "httpx", "pymongo", "subprocess", "socket", "argparse", "input(",
            "asyncio.run", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
