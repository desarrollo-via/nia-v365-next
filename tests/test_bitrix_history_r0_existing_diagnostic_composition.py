import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_existing_diagnostic_composition import (
    PreparedExistingHistoryDiagnosticComposition,
    compose_existing_history_diagnostic_preview,
    preview_existing_history_diagnostic_composition,
)


ROOT = Path(__file__).resolve().parents[1]


class ExistingHistoryDiagnosticCompositionTests(unittest.TestCase):
    def test_preview_binds_exact_graph_and_keeps_all_calls_zero(self):
        preview = preview_existing_history_diagnostic_composition()

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(preview.reason, "bitrix_history_existing_composition_prepared")
        for field in (
            "diagnostic_owner_bound",
            "protected_preflight_bound",
            "protected_resources_factory_bound",
            "history_client_builder_bound",
        ):
            self.assertTrue(getattr(preview, field), field)
        self.assertEqual(preview.dialog_read_budget, 1)
        self.assertEqual(preview.history_read_budget, 1)
        for field in (
            "diagnostic_owner_calls",
            "preflight_calls",
            "resources_factory_calls",
            "history_client_builder_calls",
            "dialog_read_calls",
            "history_read_calls",
            "wait_calls",
            "message_requests",
            "mutation_calls",
            "oauth_refresh_calls",
            "external_calls",
        ):
            self.assertEqual(getattr(preview, field), 0, field)
        self.assertTrue(preview.connector_locked_off)
        self.assertFalse(preview.persisted)
        self.assertFalse(preview.nia_called)
        self.assertFalse(preview.bitrix_written)
        self.assertFalse(preview.source_open_authorized)
        self.assertFalse(preview.real_execution_authorized)
        self.assertFalse(preview.command_available)

    def test_injected_doubles_are_bound_but_never_invoked(self):
        calls = {name: 0 for name in ("owner", "preflight", "resources", "client")}

        def spy(name):
            def dependency(*_args, **_kwargs):
                calls[name] += 1
                raise AssertionError(f"{name} must not run")
            return dependency

        preview = preview_existing_history_diagnostic_composition(
            compose_owner=lambda: compose_existing_history_diagnostic_preview(
                diagnostic_owner=spy("owner"),
                protected_preflight=spy("preflight"),
                protected_resources_factory=spy("resources"),
                history_client_builder=spy("client"),
            )
        )

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(calls, {name: 0 for name in calls})

    def test_composed_object_is_redacted_and_not_invocable(self):
        composition = compose_existing_history_diagnostic_preview()

        self.assertIs(type(composition), PreparedExistingHistoryDiagnosticComposition)
        self.assertEqual(
            repr(composition),
            "PreparedExistingHistoryDiagnosticComposition(<redacted>)",
        )
        self.assertFalse(callable(composition))
        self.assertFalse(hasattr(composition, "execute"))

    def test_invalid_dependency_or_result_fails_closed(self):
        invalid_dependency = preview_existing_history_diagnostic_composition(
            compose_owner=lambda: compose_existing_history_diagnostic_preview(
                protected_resources_factory=None
            )
        )
        invalid_result = preview_existing_history_diagnostic_composition(
            compose_owner=lambda: object()
        )

        self.assertEqual(invalid_dependency.state, "NO-GO")
        self.assertEqual(invalid_result.state, "NO-GO")
        self.assertEqual(invalid_dependency.external_calls, 0)
        self.assertEqual(invalid_result.external_calls, 0)

    def test_source_has_no_invocation_wait_message_or_external_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_existing_diagnostic_composition.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            ".open(",
            "os.environ",
            "load_dotenv",
            "get_access_token(",
            "refresh_access_token(",
            "get_dialog(",
            "get_session_history(",
            "sleep(",
            "waiting-message",
            "send_message",
            "input(",
            "asyncio.run",
            "httpx.",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
