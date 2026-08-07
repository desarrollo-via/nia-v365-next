import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_cli import (
    PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
    main,
)


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_TOKEN = "fictional-m5-token"
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m5.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m5-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m5-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m5-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m5.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m5-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m5-installations",
}


def fixture_payload() -> bytes:
    return (
        "\n".join(f"{name}={value}" for name, value in FICTIONAL_VALUES.items())
        + "\n"
    ).encode("utf-8")


class FakeProvider:
    def __init__(self, *, cancelled: bool = False) -> None:
        self.cancelled = cancelled
        self.get_calls = 0
        self.refresh_calls = 0

    async def get_access_token(self, _member_id: str) -> str:
        self.get_calls += 1
        if self.cancelled:
            raise asyncio.CancelledError
        return FICTIONAL_TOKEN

    async def refresh_access_token(self, *_args) -> None:
        self.refresh_calls += 1
        raise AssertionError("refresh must not run")


class FakeResources:
    def __init__(self, provider=None) -> None:
        self.oauth_provider = provider or FakeProvider()
        self.portal_url = "https://fictional-m5.bitrix24.invalid"
        self.member_id = "fictional-m5-member"
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeFactory:
    def __init__(self, resources: FakeResources) -> None:
        self.resources = resources
        self.build_calls = 0

    async def build(self, _settings, *, timeout_seconds: float):
        self.build_calls += 1
        if timeout_seconds != 10.0:
            raise AssertionError("unexpected timeout")
        return self.resources


class FakeClient:
    def __init__(self) -> None:
        self.dialog_calls = 0
        self.closed = False

    async def get_dialog(self, _dialog_id: str) -> BitrixHistoryReadResult:
        self.dialog_calls += 1
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.SUCCESS,
            dialog=BitrixHistoryDialog.model_validate(
                {
                    "id": 78733,
                    "dialog_id": "chat78733",
                    "entity_type": "LINES",
                    "entity_data_1": "a|b|c|d|e|900",
                    "role": "guest",
                    "last_message_id": 700,
                }
            ),
            http_status=200,
        )

    async def close(self) -> None:
        self.closed = True


class ProtectedPreflightCliTests(unittest.TestCase):
    def _run(self, argv, *, resources_factory=None, client_builder=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = main(
                argv,
                resources_factory=resources_factory,
                client_builder=client_builder,
            )
        return exit_code, output.getvalue()

    def test_owned_entrypoint_runs_complete_fixture_flow_once(self):
        resources = FakeResources()
        factory = FakeFactory(resources)
        client = FakeClient()
        client_builds = 0

        def client_builder(**values):
            nonlocal client_builds
            client_builds += 1
            self.assertEqual(values["access_token"], FICTIONAL_TOKEN)
            return client

        with tempfile.TemporaryDirectory(prefix="nia-next-r0-m5-") as directory:
            fixture_path = Path(directory) / "protected-fixture.env"
            fixture_path.write_bytes(fixture_payload())
            exit_code, raw = self._run(
                [
                    "--confirm-code",
                    PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
                    "--dotenv-path",
                    str(fixture_path),
                ],
                resources_factory=factory,
                client_builder=client_builder,
            )
            self.assertNotIn(str(fixture_path), raw)

        payload = json.loads(raw)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "READY")
        self.assertEqual(payload["reason"], "protected_preflight_ready")
        self.assertEqual(payload["failure_category"], "none")
        self.assertEqual(payload["source_read_calls"], 7)
        self.assertEqual(payload["preflight_calls"], 1)
        self.assertEqual(payload["dialog_read_calls"], 1)
        self.assertEqual(payload["history_read_calls"], 0)
        self.assertEqual(payload["mutation_calls"], 0)
        self.assertTrue(payload["resources_closed"])
        self.assertEqual(factory.build_calls, 1)
        self.assertEqual(resources.oauth_provider.get_calls, 1)
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(client_builds, 1)
        self.assertTrue(client.closed)
        self.assertTrue(resources.closed)
        self.assertNotIn(FICTIONAL_TOKEN, raw)
        for value in FICTIONAL_VALUES.values():
            self.assertNotIn(value, raw)

    def test_wrong_phrase_or_shape_stops_before_path_and_dependencies(self):
        private_path = "private-fixture-path.env"
        cases = (
            ["--confirm-code", "NO AUTORIZADO", "--dotenv-path", private_path],
            ["--dotenv-path", private_path],
        )
        for argv in cases:
            with self.subTest(argv_length=len(argv)):
                exit_code, raw = self._run(argv)
                payload = json.loads(raw)
                self.assertEqual(exit_code, 2)
                self.assertEqual(payload["reason"], "protected_preflight_cli_rejected")
                self.assertTrue(payload["resources_closed"])
                self.assertNotIn(private_path, raw)
                self.assertNotIn("NO AUTORIZADO", raw)

    def test_missing_dependencies_never_opens_explicit_path(self):
        private_path = "missing-private-fixture.env"
        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ]
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "protected_preflight_dependencies_required")
        self.assertTrue(payload["resources_closed"])
        self.assertNotIn(private_path, raw)

    def test_missing_file_with_fakes_fails_closed_before_resources(self):
        resources = FakeResources()
        factory = FakeFactory(resources)
        client = FakeClient()
        private_path = "missing-protected-fixture.env"

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ],
            resources_factory=factory,
            client_builder=lambda **_values: client,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_failed_safe")
        self.assertEqual(
            payload["failure_category"],
            "protected_source_or_settings_failed",
        )
        self.assertEqual(factory.build_calls, 0)
        self.assertTrue(payload["resources_closed"])
        self.assertNotIn(private_path, raw)

    def test_cancellation_returns_fixed_code_after_cleanup(self):
        resources = FakeResources(FakeProvider(cancelled=True))
        factory = FakeFactory(resources)
        client = FakeClient()

        with tempfile.TemporaryDirectory(prefix="nia-next-r0-m5-") as directory:
            fixture_path = Path(directory) / "protected-fixture.env"
            fixture_path.write_bytes(fixture_payload())
            exit_code, raw = self._run(
                [
                    "--confirm-code",
                    PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
                    "--dotenv-path",
                    str(fixture_path),
                ],
                resources_factory=factory,
                client_builder=lambda **_values: client,
            )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 130)
        self.assertEqual(payload["state"], "CANCELLED")
        self.assertEqual(payload["reason"], "protected_preflight_cancelled")
        self.assertEqual(payload["failure_category"], "cancelled")
        self.assertTrue(payload["resources_closed"])
        self.assertTrue(resources.closed)

    def test_module_has_no_real_dependency_selector_or_external_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_preflight_cli.py"
        ).read_text(encoding="utf-8")
        self.assertIn(PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION, source)
        for forbidden in (
            "PilotDiscoveryOAuthFactory",
            "BitrixHistoryR0Client",
            "os.environ",
            "load_dotenv",
            "keyring",
            "httpx",
            "requests",
            "pymongo",
            "motor",
            "refresh_access_token",
            "imopenlines",
            "subprocess",
            "socket",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
