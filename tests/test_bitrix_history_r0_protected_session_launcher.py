import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_launcher import (
    PreparedProtectedHistorySessionLauncher,
    compose_real_ready_protected_history_session_launcher,
    preview_real_ready_protected_history_session_launcher,
)


ROOT = Path(__file__).resolve().parents[1]


class ProtectedHistorySessionLauncherTests(unittest.TestCase):
    def test_default_real_ready_preview_binds_every_reference_without_calls(self):
        snapshot = preview_real_ready_protected_history_session_launcher()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(
            snapshot.reason,
            "protected_history_session_launcher_prepared",
        )
        self.assertTrue(snapshot.launcher_composed)
        self.assertTrue(snapshot.session_entrypoint_bound)
        self.assertTrue(snapshot.owner_preparer_bound)
        self.assertTrue(snapshot.resources_factory_builder_bound)
        self.assertTrue(snapshot.preflight_client_builder_bound)
        self.assertTrue(snapshot.armed_reader_composer_bound)
        self.assertTrue(snapshot.reader_client_builder_bound)
        for name, value in asdict(snapshot).items():
            if name.endswith("_calls"):
                self.assertEqual(value, 0, name)

    def test_injected_preview_never_invokes_any_dependency(self):
        calls = {
            "entrypoint": 0,
            "owner": 0,
            "factory": 0,
            "preflight_client": 0,
            "composer": 0,
            "reader_client": 0,
        }

        def dependency(name):
            def fail_if_called(*_args, **_kwargs):
                calls[name] += 1
                raise AssertionError(f"{name} must not run")

            return fail_if_called

        def compose_launcher():
            return compose_real_ready_protected_history_session_launcher(
                session_entrypoint=dependency("entrypoint"),
                owner_preparer=dependency("owner"),
                resources_factory_builder=dependency("factory"),
                preflight_client_builder=dependency("preflight_client"),
                armed_reader_composer=dependency("composer"),
                reader_client_builder=dependency("reader_client"),
            )

        snapshot = preview_real_ready_protected_history_session_launcher(
            compose_launcher=compose_launcher
        )

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(calls, {name: 0 for name in calls})

    def test_prepared_launcher_is_redacted_and_not_invocable(self):
        dependency = lambda *_args, **_kwargs: None
        launcher = compose_real_ready_protected_history_session_launcher(
            session_entrypoint=dependency,
            owner_preparer=dependency,
            resources_factory_builder=dependency,
            preflight_client_builder=dependency,
            armed_reader_composer=dependency,
            reader_client_builder=dependency,
        )

        self.assertIsInstance(launcher, PreparedProtectedHistorySessionLauncher)
        self.assertFalse(callable(launcher))
        self.assertEqual(
            repr(launcher),
            "PreparedProtectedHistorySessionLauncher(<redacted>)",
        )

    def test_invalid_or_failed_composition_is_redacted_no_go(self):
        with self.assertRaisesRegex(
            TypeError,
            "protected_history_session_launcher_dependency_invalid",
        ):
            compose_real_ready_protected_history_session_launcher(
                session_entrypoint=None,
            )

        snapshot = preview_real_ready_protected_history_session_launcher(
            compose_launcher=lambda: (_ for _ in ()).throw(
                RuntimeError("fictional-m14-private-detail")
            )
        )
        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.reason,
            "protected_history_session_launcher_failed_safe",
        )
        self.assertNotIn("private-detail", repr(asdict(snapshot)))
        self.assertEqual(snapshot.external_calls, 0)

    def test_source_binds_real_types_without_execution_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_launcher.py"
        ).read_text(encoding="utf-8")
        for expected in (
            "execute_protected_history_session_entrypoint_once",
            "prepare_protected_dotenv_history_handoff_once",
            "PilotDiscoveryOAuthFactory",
            "BitrixHistoryR0Client",
            "compose_stored_oauth_history_armed_reader",
        ):
            self.assertIn(expected, source)
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "keyring",
            "get_access_token",
            "refresh_access_token",
            "get_dialog(",
            "get_session_history(",
            "imopenlines",
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
