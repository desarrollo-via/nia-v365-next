import contextlib
import io
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
)
from bitrix_connector.bitrix_history_r0_protected_settings_composition import (
    execute_protected_dotenv_settings_once,
)
from bitrix_connector.config import load_settings
from bitrix_connector.modes import ConnectorMode


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m3.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m3-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m3-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m3-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m3.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m3-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m3-installations",
}


def fixture_payload(*, omit: str | None = None) -> bytes:
    return (
        "\n".join(
            f"{name}={value}"
            for name, value in FICTIONAL_VALUES.items()
            if name != omit
        )
        + "\n"
    ).encode("utf-8")


class ProtectedSettingsCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def _execute(self, payload: bytes, operation, **kwargs):
        with tempfile.TemporaryDirectory(prefix="nia-next-r0-m3-") as directory:
            fixture_path = Path(directory) / "protected-fixture.env"
            fixture_path.write_bytes(payload)
            snapshot = await execute_protected_dotenv_settings_once(
                dotenv_path=fixture_path,
                operation=operation,
                **kwargs,
            )
            return snapshot, str(fixture_path)

    async def test_real_loader_composes_safe_settings_from_fixture_once(self):
        operation_calls = 0

        async def operation(settings):
            nonlocal operation_calls
            operation_calls += 1
            self.assertEqual(settings.effective_mode, ConnectorMode.OFF)
            self.assertTrue(settings.activation_locked)
            self.assertFalse(settings.external_calls_enabled)
            self.assertFalse(settings.installation_enabled)
            self.assertFalse(settings.r0_bridge_enabled)
            self.assertFalse(settings.pilot_enabled)
            self.assertTrue(settings.pilot_emergency_stop)
            self.assertEqual(settings.bitrix_domain, FICTIONAL_VALUES["NIA_BITRIX_DOMAIN"])
            self.assertEqual(settings.mongo_uri, FICTIONAL_VALUES["NIA_BITRIX_MONGO_URI"])

        snapshot, _path = await self._execute(fixture_payload(), operation)

        self.assertEqual(snapshot.state, ProtectedHelperState.READY)
        self.assertTrue(snapshot.required_values_present)
        self.assertTrue(snapshot.operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.source_read_calls, 7)
        self.assertEqual(snapshot.operation_calls, 1)
        self.assertEqual(operation_calls, 1)

    async def test_injected_loader_receives_only_allowlisted_mapping(self):
        loader_calls = 0
        observed_names = ()

        def settings_loader(environment):
            nonlocal loader_calls, observed_names
            loader_calls += 1
            observed_names = tuple(environment)
            self.assertEqual(repr(environment), "_ProtectedSettingsEnvironment(<redacted>)")
            self.assertIsNone(environment.get("NIA_BITRIX_MODE"))
            return load_settings(environment)

        async def operation(_settings):
            return None

        snapshot, _path = await self._execute(
            fixture_payload(),
            operation,
            settings_loader=settings_loader,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.READY)
        self.assertEqual(loader_calls, 1)
        self.assertEqual(observed_names, PROTECTED_SETTING_NAMES)

    async def test_missing_value_fails_before_loader_and_operation(self):
        loader_calls = 0
        operation_calls = 0

        def settings_loader(environment):
            nonlocal loader_calls
            loader_calls += 1
            return load_settings(environment)

        async def operation(_settings):
            nonlocal operation_calls
            operation_calls += 1

        snapshot, _path = await self._execute(
            fixture_payload(omit=PROTECTED_SETTING_NAMES[4]),
            operation,
            settings_loader=settings_loader,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(snapshot.source_read_calls, 0)
        self.assertEqual(snapshot.operation_calls, 0)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(loader_calls, 0)
        self.assertEqual(operation_calls, 0)

    async def test_degraded_settings_fail_before_operation(self):
        operation_calls = 0

        def degraded_loader(_environment):
            return load_settings({"NIA_BITRIX_MODE": "active"})

        async def operation(_settings):
            nonlocal operation_calls
            operation_calls += 1

        snapshot, _path = await self._execute(
            fixture_payload(),
            operation,
            settings_loader=degraded_loader,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(snapshot.reason, "protected_helper_failed_safe")
        self.assertFalse(snapshot.operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(operation_calls, 0)

    async def test_failure_output_redacts_path_names_and_values(self):
        async def operation(_settings):
            raise RuntimeError("fictional-m3-private-detail")

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            snapshot, fixture_path = await self._execute(
                fixture_payload(),
                operation,
            )
        serialized = repr(asdict(snapshot)) + output.getvalue()

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertTrue(snapshot.resources_closed)
        self.assertNotIn(fixture_path, serialized)
        self.assertNotIn("fictional-m3-private-detail", serialized)
        for name, value in FICTIONAL_VALUES.items():
            self.assertNotIn(name, serialized)
            self.assertNotIn(value, serialized)

    def test_composition_has_no_cli_environment_network_or_service_access(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_settings_composition.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "keyring",
            "httpx",
            "requests",
            "pymongo",
            "motor",
            "get_access_token",
            "refresh_access_token",
            "imopenlines",
            "subprocess",
            "socket",
            "argparse",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
