import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_oauth_refresh_execution_owner import (
    OAUTH_REFRESH_FUTURE_AUTHORIZATION,
    OAUTH_REFRESH_OWNER_COMMAND,
    OAUTH_REFRESH_OWNER_READINESS,
    OAUTH_REFRESH_REAL_CONFIRMATION,
    OAuthRefreshExecutionSnapshot,
    execute_protected_oauth_refresh_once,
    main,
)


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional-oauth.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-oauth-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-oauth-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional-oauth-secret",
    "NIA_BITRIX_MONGO_URI": "mongodb://fictional-oauth.invalid",
    "NIA_BITRIX_MONGO_DB": "fictional-oauth-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-oauth-installations",
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


class FakeProvider:
    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.current = "fictional-stale-token"
        self.get_calls = 0
        self.refresh_calls = 0

    async def get_access_token(self, _member_id: str) -> str:
        self.get_calls += 1
        return self.current

    async def refresh_access_token(self, _member_id: str, stale: str) -> str:
        self.refresh_calls += 1
        if self.failure is not None:
            raise self.failure
        if stale != self.current:
            raise AssertionError("stale token mismatch")
        self.current = "fictional-refreshed-token"
        return self.current


class FakeResources:
    def __init__(self, provider: FakeProvider, *, close_failure: bool = False) -> None:
        self.oauth_provider = provider
        self.member_id = "fictional-oauth-member"
        self.close_failure = close_failure
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_failure:
            raise RuntimeError("fictional-private-close-detail")


class FakeFactory:
    def __init__(self, resources: FakeResources) -> None:
        self.resources = resources
        self.build_calls = 0

    async def build(self, _settings, *, timeout_seconds: float):
        self.build_calls += 1
        if timeout_seconds != 10.0:
            raise AssertionError("unexpected timeout")
        return self.resources


class OAuthRefreshCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def _execute(self, payload: bytes, resources: FakeResources):
        with tempfile.TemporaryDirectory(prefix="nia-next-oauth-owner-") as directory:
            fixture = Path(directory) / "protected-fixture.env"
            fixture.write_bytes(payload)
            factory = FakeFactory(resources)
            snapshot = await execute_protected_oauth_refresh_once(
                dotenv_path=fixture,
                resources_factory=factory,
            )
            return snapshot, factory, str(fixture)

    async def test_ready_renews_once_verifies_persistence_and_closes(self):
        provider = FakeProvider()
        resources = FakeResources(provider)
        snapshot, factory, _path = await self._execute(
            fixture_payload(), resources
        )

        self.assertEqual(snapshot.state, "READY")
        self.assertEqual(snapshot.reason, "oauth_rotated_and_persisted")
        self.assertTrue(snapshot.protected_source_opened)
        self.assertTrue(snapshot.required_values_present)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.source_read_calls, 7)
        self.assertEqual(snapshot.settings_operation_calls, 1)
        self.assertEqual(snapshot.resource_build_calls, 1)
        self.assertEqual(snapshot.access_token_read_calls, 1)
        self.assertEqual(snapshot.refresh_method_calls, 1)
        self.assertEqual(snapshot.persistence_verification_calls, 1)
        self.assertTrue(snapshot.token_rotated)
        self.assertTrue(snapshot.persistence_verified)
        self.assertEqual(snapshot.bitrix_api_calls, 0)
        self.assertEqual(snapshot.history_read_calls, 0)
        self.assertEqual(snapshot.mutation_calls, 0)
        self.assertFalse(snapshot.nia_called)
        self.assertFalse(snapshot.bitrix_written)
        self.assertEqual(factory.build_calls, 1)
        self.assertEqual(provider.get_calls, 2)
        self.assertEqual(provider.refresh_calls, 1)
        self.assertEqual(resources.close_calls, 1)

    async def test_missing_value_stops_before_resource_build(self):
        provider = FakeProvider()
        resources = FakeResources(provider)
        snapshot, factory, _path = await self._execute(
            fixture_payload(omit="NIA_BITRIX_CLIENT_SECRET"), resources
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "oauth_refresh_failed_safe")
        self.assertEqual(snapshot.source_read_calls, 0)
        self.assertEqual(snapshot.refresh_method_calls, 0)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(factory.build_calls, 0)
        self.assertEqual(resources.close_calls, 0)

    async def test_refresh_failure_is_redacted_and_resources_close(self):
        private_detail = "fictional-private-refresh-detail"
        provider = FakeProvider(failure=RuntimeError(private_detail))
        resources = FakeResources(provider)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            snapshot, _factory, path = await self._execute(
                fixture_payload(), resources
            )
        serialized = repr(asdict(snapshot)) + output.getvalue()

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "oauth_refresh_failed_safe")
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.refresh_method_calls, 1)
        self.assertFalse(snapshot.token_rotated)
        self.assertFalse(snapshot.persistence_verified)
        self.assertEqual(resources.close_calls, 1)
        self.assertNotIn(private_detail, serialized)
        self.assertNotIn(path, serialized)
        for name, value in FICTIONAL_VALUES.items():
            self.assertNotIn(name, serialized)
            self.assertNotIn(value, serialized)

    async def test_close_failure_is_terminal(self):
        resources = FakeResources(FakeProvider(), close_failure=True)
        snapshot, _factory, _path = await self._execute(
            fixture_payload(), resources
        )
        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "oauth_refresh_resources_close_failed")
        self.assertFalse(snapshot.resources_closed)
        self.assertFalse(snapshot.token_rotated)
        self.assertFalse(snapshot.persistence_verified)

    async def test_cancellation_is_terminal_and_closes(self):
        resources = FakeResources(FakeProvider(failure=asyncio.CancelledError()))
        snapshot, _factory, _path = await self._execute(
            fixture_payload(), resources
        )
        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertEqual(snapshot.reason, "oauth_refresh_cancelled")
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(resources.close_calls, 1)


class OAuthRefreshOwnerCliTests(unittest.TestCase):
    def _run(self, argv, *, executor):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = main(argv, executor=executor)
        return exit_code, output.getvalue()

    def test_wrong_phrase_rejects_before_executor(self):
        calls = 0

        async def executor(**_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("executor must not run")

        exit_code, raw = self._run(
            ["--confirm-code", "NO AUTORIZADO", "--dotenv-path", "private.env"],
            executor=executor,
        )
        payload = json.loads(raw)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "oauth_refresh_owner_rejected")
        self.assertEqual(calls, 0)
        self.assertNotIn("private.env", raw)

    def test_valid_request_calls_executor_once_and_redacts_path(self):
        calls = []

        async def executor(*, dotenv_path):
            calls.append(dotenv_path)
            return OAuthRefreshExecutionSnapshot(
                state="READY",
                reason="oauth_rotated_and_persisted",
                protected_source_opened=True,
                required_values_present=True,
                resources_closed=True,
                source_read_calls=7,
                settings_operation_calls=1,
                resource_build_calls=1,
                access_token_read_calls=1,
                refresh_method_calls=1,
                persistence_verification_calls=1,
                token_rotated=True,
                persistence_verified=True,
            )

        private_path = "fictional-private-owner.env"
        exit_code, raw = self._run(
            [
                "--confirm-code",
                OAUTH_REFRESH_REAL_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ],
            executor=executor,
        )
        payload = json.loads(raw)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "READY")
        self.assertEqual(payload["refresh_method_calls"], 1)
        self.assertEqual(calls, [Path(private_path)])
        self.assertNotIn(private_path, raw)

    def test_executor_failure_is_redacted(self):
        private_detail = "fictional-owner-private-detail"

        async def executor(**_kwargs):
            raise RuntimeError(private_detail)

        exit_code, raw = self._run(
            [
                "--confirm-code",
                OAUTH_REFRESH_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-failure.env",
            ],
            executor=executor,
        )
        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "oauth_refresh_owner_failed_safe")
        self.assertFalse(payload["resources_closed"])
        self.assertNotIn(private_detail, raw)
        self.assertNotIn("private-failure.env", raw)

    def test_readiness_and_command_are_frozen_but_not_authorized(self):
        self.assertTrue(OAUTH_REFRESH_OWNER_READINESS.command_available)
        self.assertTrue(OAUTH_REFRESH_OWNER_READINESS.owner_module_invocable)
        self.assertFalse(OAUTH_REFRESH_OWNER_READINESS.authorization_ready_for_use)
        self.assertTrue(OAUTH_REFRESH_OWNER_READINESS.two_confirmations_required)
        self.assertFalse(OAUTH_REFRESH_OWNER_READINESS.exact_rollback_available)
        self.assertFalse(OAUTH_REFRESH_OWNER_READINESS.real_execution_authorized)
        self.assertFalse(OAUTH_REFRESH_OWNER_READINESS.source_open_authorized)
        self.assertFalse(OAUTH_REFRESH_OWNER_READINESS.oauth_refresh_authorized)
        self.assertIn("bitrix_oauth_refresh_execution_owner", OAUTH_REFRESH_OWNER_COMMAND)
        self.assertIn(OAUTH_REFRESH_REAL_CONFIRMATION, OAUTH_REFRESH_OWNER_COMMAND)
        self.assertIn(OAUTH_REFRESH_OWNER_COMMAND, OAUTH_REFRESH_FUTURE_AUTHORIZATION)
        for name in FICTIONAL_VALUES:
            self.assertIn(name, OAUTH_REFRESH_FUTURE_AUTHORIZATION)
        self.assertIn("No autorizo reintentos", OAUTH_REFRESH_FUTURE_AUTHORIZATION)

    def test_owner_has_no_bitrix_rest_or_message_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_oauth_refresh_execution_owner.py"
        ).read_text(encoding="utf-8")
        before_authorization, after_authorization = source.split(
            "OAUTH_REFRESH_FUTURE_AUTHORIZATION = (", 1
        )
        _contract, executable_tail = after_authorization.split(
            "DEFAULT_OAUTH_REFRESH_TIMEOUT_SECONDS", 1
        )
        executable_source = (
            before_authorization
            + "DEFAULT_OAUTH_REFRESH_TIMEOUT_SECONDS"
            + executable_tail
        )
        for forbidden in (
            "BitrixHistoryR0Client",
            "get_dialog",
            "get_session_history",
            "imopenlines",
            "config.update",
            "send_message",
            "requests",
            "subprocess",
            "socket",
            "load_dotenv",
            "os.environ",
        ):
            self.assertNotIn(forbidden, executable_source)


if __name__ == "__main__":
    unittest.main()
