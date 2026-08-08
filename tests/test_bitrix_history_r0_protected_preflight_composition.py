import asyncio
import contextlib
import io
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_composition import (
    execute_protected_dotenv_preflight_once,
)


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_TOKEN = "fictional-m4-token"
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-m4.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-m4-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-m4-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-m4-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-m4.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-m4-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-m4-installations",
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


def successful_read(
    *,
    chat_id: int = 78733,
    dialog_id: str | None = None,
    entity_type: str = "LINES",
    role: str = "guest",
) -> BitrixHistoryReadResult:
    return BitrixHistoryReadResult(
        decision=BitrixHistoryReadDecision.SUCCESS,
        dialog=BitrixHistoryDialog.model_validate(
            {
                "id": chat_id,
                "dialog_id": dialog_id or f"chat{chat_id}",
                "entity_type": entity_type,
                "entity_data_1": "a|b|c|d|e|900",
                "role": role,
                "last_message_id": 700,
            }
        ),
        http_status=200,
    )


class FakeProvider:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.error = error
        self.get_calls = 0
        self.refresh_calls = 0

    async def get_access_token(self, _member_id: str) -> str:
        self.get_calls += 1
        if self.error is not None:
            raise self.error
        return FICTIONAL_TOKEN

    async def refresh_access_token(self, *_args) -> None:
        self.refresh_calls += 1
        raise AssertionError("refresh must not run")


class FakeResources:
    def __init__(self, provider=None, *, close_error: bool = False) -> None:
        self.oauth_provider = provider or FakeProvider()
        self.portal_url = "https://fictional-m4.bitrix24.invalid"
        self.member_id = "fictional-m4-member"
        self.close_error = close_error
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        if self.close_error:
            raise RuntimeError("fictional-m4-resource-close-detail")


class FakeResourcesFactory:
    def __init__(self, resources: FakeResources) -> None:
        self.resources = resources
        self.build_calls = 0

    async def build(self, _settings, *, timeout_seconds: float):
        self.build_calls += 1
        if timeout_seconds != 10.0:
            raise AssertionError("unexpected timeout")
        return self.resources


class FakeClient:
    def __init__(self, read_result=None, *, close_error: bool = False) -> None:
        self.read_result = read_result or successful_read()
        self.close_error = close_error
        self.dialog_calls = 0
        self.closed = False

    async def get_dialog(self, _dialog_id: str) -> BitrixHistoryReadResult:
        self.dialog_calls += 1
        return self.read_result

    async def close(self) -> None:
        self.closed = True
        if self.close_error:
            raise RuntimeError("fictional-m4-client-close-detail")


class ProtectedPreflightCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def _execute(self, payload: bytes, resources, client, **kwargs):
        with tempfile.TemporaryDirectory(prefix="nia-next-r0-m4-") as directory:
            fixture_path = Path(directory) / "protected-fixture.env"
            fixture_path.write_bytes(payload)
            factory = FakeResourcesFactory(resources)
            client_build_calls = 0

            def client_builder(**builder_values):
                nonlocal client_build_calls
                client_build_calls += 1
                self.assertEqual(builder_values["access_token"], FICTIONAL_TOKEN)
                self.assertEqual(builder_values["timeout_seconds"], 10.0)
                return client

            snapshot = await execute_protected_dotenv_preflight_once(
                dotenv_path=fixture_path,
                resources_factory=factory,
                client_builder=client_builder,
                **kwargs,
            )
            return snapshot, factory, client_build_calls, str(fixture_path)

    async def test_end_to_end_ready_uses_one_fake_resource_and_read(self):
        resources = FakeResources()
        client = FakeClient()

        snapshot, factory, client_build_calls, _path = await self._execute(
            fixture_payload(), resources, client
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.READY)
        self.assertEqual(snapshot.reason, "protected_preflight_ready")
        self.assertEqual(snapshot.failure_category, "none")
        self.assertTrue(snapshot.required_values_present)
        self.assertTrue(snapshot.settings_operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.source_read_calls, 7)
        self.assertEqual(snapshot.preflight_calls, 1)
        self.assertEqual(snapshot.dialog_read_calls, 1)
        self.assertEqual(snapshot.history_read_calls, 0)
        self.assertEqual(snapshot.mutation_calls, 0)
        self.assertTrue(snapshot.anchor_available)
        self.assertTrue(snapshot.connector_locked_off)
        self.assertFalse(snapshot.persisted)
        self.assertFalse(snapshot.nia_called)
        self.assertFalse(snapshot.bitrix_written)
        self.assertEqual(factory.build_calls, 1)
        self.assertEqual(resources.oauth_provider.get_calls, 1)
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(client_build_calls, 1)
        self.assertEqual(client.dialog_calls, 1)
        self.assertTrue(client.closed)
        self.assertTrue(resources.closed)

    async def test_missing_source_value_stops_before_resources(self):
        resources = FakeResources()
        client = FakeClient()

        snapshot, factory, client_build_calls, _path = await self._execute(
            fixture_payload(omit=PROTECTED_SETTING_NAMES[0]), resources, client
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(
            snapshot.failure_category,
            "protected_source_or_settings_failed",
        )
        self.assertEqual(snapshot.preflight_calls, 0)
        self.assertEqual(snapshot.source_read_calls, 0)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(factory.build_calls, 0)
        self.assertEqual(client_build_calls, 0)
        self.assertFalse(client.closed)
        self.assertFalse(resources.closed)

    async def test_dialog_mismatch_maps_to_fixed_no_go_and_discards_anchor(self):
        resources = FakeResources()
        client = FakeClient(successful_read(chat_id=78734))

        snapshot, factory, _builds, _path = await self._execute(
            fixture_payload(), resources, client
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(snapshot.reason, "protected_preflight_no_go")
        self.assertEqual(snapshot.failure_category, "dialog_identity_mismatch")
        self.assertFalse(snapshot.anchor_available)
        self.assertEqual(snapshot.dialog_read_calls, 1)
        self.assertEqual(factory.build_calls, 1)
        self.assertTrue(snapshot.resources_closed)
        self.assertTrue(snapshot.identity_diagnostic_available)
        self.assertFalse(snapshot.chat_id_matches)
        self.assertFalse(snapshot.dialog_id_matches)
        self.assertTrue(snapshot.entity_type_matches)
        self.assertTrue(snapshot.role_allowed)
        self.assertEqual(snapshot.identity_mismatch_count, 2)

    async def test_each_identity_comparison_is_public_only_as_a_boolean(self):
        cases = (
            (
                successful_read(chat_id=78734, dialog_id="chat78733"),
                (False, True, True, True),
            ),
            (
                successful_read(dialog_id="chat78734"),
                (True, False, True, True),
            ),
            (
                successful_read(entity_type="OPENLINES"),
                (True, True, False, True),
            ),
            (
                successful_read(role="   "),
                (True, True, True, False),
            ),
        )
        for read_result, expected in cases:
            with self.subTest(expected=expected):
                snapshot, _factory, _builds, _path = await self._execute(
                    fixture_payload(),
                    FakeResources(),
                    FakeClient(read_result),
                )
                self.assertEqual(snapshot.failure_category, "dialog_identity_mismatch")
                self.assertTrue(snapshot.identity_diagnostic_available)
                self.assertEqual(
                    (
                        snapshot.chat_id_matches,
                        snapshot.dialog_id_matches,
                        snapshot.entity_type_matches,
                        snapshot.role_allowed,
                    ),
                    expected,
                )
                self.assertEqual(snapshot.identity_mismatch_count, 1)

    async def test_non_identity_results_do_not_publish_identity_diagnostic(self):
        snapshot, _factory, _builds, _path = await self._execute(
            fixture_payload(), FakeResources(), FakeClient()
        )

        self.assertEqual(snapshot.failure_category, "none")
        self.assertFalse(snapshot.identity_diagnostic_available)
        self.assertFalse(snapshot.chat_id_matches)
        self.assertFalse(snapshot.dialog_id_matches)
        self.assertFalse(snapshot.entity_type_matches)
        self.assertFalse(snapshot.role_allowed)
        self.assertEqual(snapshot.identity_mismatch_count, 0)

    async def test_private_failure_details_are_never_public(self):
        resources = FakeResources(
            FakeProvider(error=RuntimeError("fictional-m4-private-detail"))
        )
        client = FakeClient()
        output = io.StringIO()

        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            snapshot, _factory, _builds, fixture_path = await self._execute(
                fixture_payload(), resources, client
            )
        serialized = repr(asdict(snapshot)) + output.getvalue()

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(snapshot.reason, "protected_preflight_no_go")
        self.assertEqual(snapshot.failure_category, "oauth_or_resources_failed")
        self.assertTrue(snapshot.resources_closed)
        self.assertNotIn(fixture_path, serialized)
        self.assertNotIn("fictional-m4-private-detail", serialized)
        self.assertNotIn(FICTIONAL_TOKEN, serialized)
        for name, value in FICTIONAL_VALUES.items():
            self.assertNotIn(name, serialized)
            self.assertNotIn(value, serialized)

    async def test_any_close_failure_is_terminal(self):
        cases = (
            (FakeResources(close_error=True), FakeClient()),
            (FakeResources(), FakeClient(close_error=True)),
        )
        for resources, client in cases:
            with self.subTest(resource_close_error=resources.close_error):
                snapshot, _factory, _builds, _path = await self._execute(
                    fixture_payload(), resources, client
                )
                self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
                self.assertEqual(snapshot.reason, "protected_preflight_close_failed")
                self.assertEqual(snapshot.failure_category, "resources_close_failed")
                self.assertFalse(snapshot.resources_closed)
                self.assertFalse(snapshot.anchor_available)

    async def test_cancellation_closes_fake_resources_and_source(self):
        resources = FakeResources(FakeProvider(error=asyncio.CancelledError()))
        client = FakeClient()

        snapshot, factory, _builds, _path = await self._execute(
            fixture_payload(), resources, client
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.CANCELLED)
        self.assertEqual(snapshot.reason, "protected_preflight_cancelled")
        self.assertEqual(snapshot.failure_category, "cancelled")
        self.assertTrue(snapshot.resources_closed)
        self.assertFalse(snapshot.anchor_available)
        self.assertEqual(factory.build_calls, 1)
        self.assertTrue(resources.closed)

    async def test_dialog_failures_map_only_to_fixed_public_categories(self):
        cases = (
            ("bitrix_history_token_expired", "oauth_token_expired"),
            ("bitrix_history_timeout", "dialog_read_unavailable"),
            ("bitrix_history_transport_error", "dialog_read_unavailable"),
            ("bitrix_history_read_unavailable", "dialog_read_unavailable"),
            ("bitrix_history_read_rejected", "dialog_read_rejected"),
            ("bitrix_history_invalid_response", "dialog_response_invalid"),
            ("unrecognized-safe-code", "other_safe_failure"),
        )
        for error_code, expected_category in cases:
            with self.subTest(error_code=error_code):
                resources = FakeResources()
                client = FakeClient(
                    BitrixHistoryReadResult(
                        decision=BitrixHistoryReadDecision.FAIL,
                        error_code=error_code,
                    )
                )
                snapshot, _factory, _builds, _path = await self._execute(
                    fixture_payload(), resources, client
                )
                self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
                self.assertEqual(snapshot.reason, "protected_preflight_no_go")
                self.assertEqual(snapshot.failure_category, expected_category)
                self.assertNotIn(error_code, repr(asdict(snapshot)))

    def test_module_requires_injected_resources_and_has_no_external_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_preflight_composition.py"
        ).read_text(encoding="utf-8")
        self.assertIn("resources_factory: StoredOAuthResourcesFactory", source)
        self.assertIn("client_builder: BitrixHistoryClientBuilder", source)
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
            "argparse",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
