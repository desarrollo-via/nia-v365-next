import contextlib
import io
import json
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_preflight_launcher import (
    PROTECTED_PREFLIGHT_LAUNCHER_CONFIRMATION,
    PreparedProtectedPreflightLauncher,
    compose_real_ready_launcher,
    main,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, _settings, *, timeout_seconds):
        raise AssertionError(f"build must not run: {timeout_seconds}")


class ProtectedPreflightLauncherTests(unittest.TestCase):
    def _run(self, argv, *, compose_launcher):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = main(argv, compose_launcher=compose_launcher)
        return exit_code, output.getvalue()

    def test_preview_composes_with_doubles_without_invoking_owner_or_path(self):
        factory_builders = 0
        owner_calls = 0
        client_calls = 0

        def resources_factory_builder():
            nonlocal factory_builders
            factory_builders += 1
            return FakeResourcesFactory()

        def client_builder(**_values):
            nonlocal client_calls
            client_calls += 1
            raise AssertionError("client must not be constructed")

        def owner(_argv, **_dependencies):
            nonlocal owner_calls
            owner_calls += 1
            raise AssertionError("owner must not run")

        def compose_launcher():
            return compose_real_ready_launcher(
                resources_factory_builder=resources_factory_builder,
                client_builder=client_builder,
                owner=owner,
            )

        private_path = "private-real-ready.env"
        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_LAUNCHER_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ],
            compose_launcher=compose_launcher,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "PREPARED")
        self.assertEqual(payload["reason"], "protected_preflight_launcher_prepared")
        self.assertTrue(payload["launcher_composed"])
        self.assertTrue(payload["owner_entrypoint_bound"])
        self.assertTrue(payload["resources_factory_bound"])
        self.assertTrue(payload["client_builder_bound"])
        self.assertEqual(payload["source_open_calls"], 0)
        self.assertEqual(payload["preflight_calls"], 0)
        self.assertEqual(payload["external_calls"], 0)
        self.assertEqual(factory_builders, 1)
        self.assertEqual(owner_calls, 0)
        self.assertEqual(client_calls, 0)
        self.assertNotIn(private_path, raw)

    def test_wrong_confirmation_stops_before_composition(self):
        compose_calls = 0

        def compose_launcher():
            nonlocal compose_calls
            compose_calls += 1
            raise AssertionError("compose must not run")

        exit_code, raw = self._run(
            [
                "--confirm-code",
                "NO AUTORIZADO",
                "--dotenv-path",
                "private.env",
            ],
            compose_launcher=compose_launcher,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "protected_preflight_launcher_rejected")
        self.assertEqual(compose_calls, 0)
        self.assertNotIn("private.env", raw)
        self.assertNotIn("NO AUTORIZADO", raw)

    def test_composition_failure_is_redacted_and_fail_closed(self):
        def compose_launcher():
            raise RuntimeError("fictional-m6-private-detail")

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_LAUNCHER_CONFIRMATION,
                "--dotenv-path",
                "private.env",
            ],
            compose_launcher=compose_launcher,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["state"], "NO-GO")
        self.assertEqual(payload["reason"], "protected_preflight_launcher_failed_safe")
        self.assertNotIn("fictional-m6-private-detail", raw)
        self.assertEqual(payload["external_calls"], 0)

    def test_composed_launcher_forwards_only_injected_dependencies(self):
        resources = FakeResourcesFactory()
        owner_calls = []

        def client_builder(**_values):
            raise AssertionError("client construction belongs to future execution")

        def owner(argv, **dependencies):
            owner_calls.append((tuple(argv), dependencies))
            return 7

        launcher = compose_real_ready_launcher(
            resources_factory_builder=lambda: resources,
            client_builder=client_builder,
            owner=owner,
        )
        exit_code = launcher(("fixture-argument",))

        self.assertEqual(exit_code, 7)
        self.assertEqual(len(owner_calls), 1)
        self.assertEqual(owner_calls[0][0], ("fixture-argument",))
        self.assertIs(owner_calls[0][1]["resources_factory"], resources)
        self.assertIs(owner_calls[0][1]["client_builder"], client_builder)
        self.assertEqual(
            repr(launcher),
            "PreparedProtectedPreflightLauncher(<redacted>)",
        )

    def test_invalid_dependency_is_rejected_before_launcher(self):
        with self.assertRaisesRegex(
            TypeError, "protected_preflight_resources_factory_invalid"
        ):
            compose_real_ready_launcher(
                resources_factory_builder=lambda: object(),
                client_builder=lambda **_values: None,
                owner=lambda _argv, **_dependencies: 0,
            )

    def test_source_selects_real_types_but_contains_no_execution_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_preflight_launcher.py"
        ).read_text(encoding="utf-8")
        self.assertIn("PilotDiscoveryOAuthFactory", source)
        self.assertIn("BitrixHistoryR0Client", source)
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "keyring",
            "get_access_token",
            "refresh_access_token",
            "get_dialog(",
            "imopenlines",
            "httpx.AsyncClient(",
            "AsyncIOMotorClient(",
            "subprocess",
            "socket",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
