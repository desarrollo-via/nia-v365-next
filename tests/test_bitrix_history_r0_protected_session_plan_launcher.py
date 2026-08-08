import asyncio
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_plan_launcher import (
    PreparedProtectedHistorySessionPlanLauncher,
    compose_real_ready_protected_history_session_plan_launcher,
    fail_closed_inner_confirmation_reader,
    preview_real_ready_protected_history_session_plan_launcher,
)


ROOT = Path(__file__).resolve().parents[1]


class ProtectedSessionPlanLauncherTests(unittest.TestCase):
    def test_default_preview_binds_every_real_reference_with_zero_calls(self):
        snapshot = preview_real_ready_protected_history_session_plan_launcher()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertTrue(snapshot.launcher_composed)
        for name, value in asdict(snapshot).items():
            if name.endswith("_bound"):
                self.assertTrue(value, name)
            if name.endswith("_calls"):
                self.assertEqual(value, 0, name)
        self.assertTrue(snapshot.confirmation_reader_fail_closed)

    def test_injected_preview_never_invokes_dependencies(self):
        names = (
            "path_builder",
            "source_builder",
            "resources_factory_builder",
            "preflight_client_builder",
            "reader_client_builder",
            "inputs_builder",
            "confirmation_reader",
            "plan_builder",
            "gate_composer",
        )
        calls = {name: 0 for name in names}

        def dependency(name):
            def fail_if_called(*_args, **_kwargs):
                calls[name] += 1
                raise AssertionError(f"{name} must not run")

            return fail_if_called

        snapshot = preview_real_ready_protected_history_session_plan_launcher(
            compose_launcher=lambda: (
                compose_real_ready_protected_history_session_plan_launcher(
                    **{name: dependency(name) for name in names}
                )
            )
        )

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(calls, {name: 0 for name in names})

    def test_launcher_is_redacted_non_invocable_and_has_no_values(self):
        launcher = compose_real_ready_protected_history_session_plan_launcher()

        self.assertIsInstance(launcher, PreparedProtectedHistorySessionPlanLauncher)
        self.assertFalse(callable(launcher))
        self.assertEqual(
            repr(launcher),
            "PreparedProtectedHistorySessionPlanLauncher(<redacted>)",
        )
        serialized = repr(launcher)
        for private in ("dotenv", "member", "hash", "window", "token"):
            self.assertNotIn(private, serialized.lower())

    def test_inner_confirmation_default_is_fail_closed(self):
        with self.assertRaisesRegex(
            RuntimeError, "protected_history_session_inner_confirmation_required"
        ):
            asyncio.run(fail_closed_inner_confirmation_reader())

    def test_invalid_or_failed_composition_is_redacted_no_go(self):
        with self.assertRaisesRegex(
            TypeError, "protected_history_session_plan_launcher_dependency_invalid"
        ):
            compose_real_ready_protected_history_session_plan_launcher(
                inputs_builder=None
            )

        snapshot = preview_real_ready_protected_history_session_plan_launcher(
            compose_launcher=lambda: (_ for _ in ()).throw(
                RuntimeError("fictional-m19-private-detail")
            )
        )
        self.assertEqual(snapshot.state, "NO-GO")
        self.assertNotIn("private-detail", repr(asdict(snapshot)))

    def test_source_contains_references_but_no_direct_execution_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_plan_launcher.py"
        ).read_text(encoding="utf-8")
        for expected in (
            "AllowlistedDotenvSource",
            "PilotDiscoveryOAuthFactory",
            "BitrixHistoryR0Client",
            "BitrixHistoryR0EphemeralInputs",
            "ProtectedHistorySessionExecutionPlan",
            "compose_protected_history_session_execution_gate",
        ):
            self.assertIn(expected, source)
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "get_access_token",
            "refresh_access_token",
            "get_dialog(",
            "get_session_history(",
            "httpx.AsyncClient(",
            "AsyncIOMotorClient(",
            "subprocess",
            "socket",
            "argparse",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
