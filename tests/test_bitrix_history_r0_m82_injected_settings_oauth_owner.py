import asyncio
import contextlib
import io
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthRecord,
    M82Status,
    StoredOAuthNoRefreshResourceOwner,
    execute_m82_injected_settings_oauth_once,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)
from bitrix_connector.config import load_settings
from bitrix_connector.modes import ConnectorMode


ROOT = Path(__file__).resolve().parents[1]


def credential_buffers():
    values = (
        "fixture-m82.invalid",
        "fixture-member",
        "fixture-client",
        "fixture-client-secret",
        "mongodb://fixture-m82.invalid",
        "fixture-db",
        "fixture-installations",
    )
    return {
        name: bytearray(value.encode())
        for name, value in zip(PROTECTED_SETTING_NAMES, values, strict=True)
    }


class CredentialMemoryBackend:
    def __init__(self, *, error=None, close_error=None):
        self.buffers = credential_buffers()
        self.record = InjectedWindowsCredentialRecord(
            target_id=M80_CREDENTIAL_TARGET_ID,
            buffers=self.buffers,
        )
        self.error = error
        self.close_error = close_error
        self.fetch_calls = 0
        self.close_calls = 0

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        if self.error is not None:
            raise self.error
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()
        if self.close_error is not None:
            raise self.close_error


class OAuthMemoryBackend:
    def __init__(self, *, record=None, error=None, close_error=None):
        self.token = bytearray(b"fixture-oauth-token")
        self.record = record if record is not None else InjectedStoredOAuthRecord(
            access_token=self.token
        )
        self.error = error
        self.close_error = close_error
        self.load_calls = 0
        self.close_calls = 0
        self.settings = None

    async def load_stored_once(self, settings):
        self.load_calls += 1
        self.settings = settings
        if self.error is not None:
            raise self.error
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if type(self.record) is InjectedStoredOAuthRecord:
            self.record.clear()
        if self.close_error is not None:
            raise self.close_error


class RefreshCapableOAuthBackend(OAuthMemoryBackend):
    async def refresh_access_token(self):
        raise AssertionError("must-not-run")


class M82InjectedSettingsOAuthOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_settings_and_stored_oauth_run_once_without_refresh(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend()
        operation_calls = 0

        async def operation(settings, token):
            nonlocal operation_calls
            operation_calls += 1
            self.assertEqual(settings.effective_mode, ConnectorMode.OFF)
            self.assertTrue(settings.activation_locked)
            self.assertFalse(settings.external_calls_enabled)
            self.assertEqual(token.read_text(), "fixture-oauth-token")

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential,
            oauth_backend=oauth,
            operation=operation,
        )

        self.assertEqual(result.status, M82Status.READY)
        self.assertEqual(result.protected_failure_category, "none")
        self.assertEqual(result.credential_source_read_calls, 7)
        self.assertEqual(result.settings_load_calls, 1)
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (1, 0))
        self.assertEqual((result.oauth_operation_calls, result.oauth_token_view_reads), (1, 1))
        self.assertTrue(result.settings_off_locked_verified)
        self.assertTrue(result.private_resources_closed)
        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
        self.assertEqual(operation_calls, 1)
        self.assertTrue(all(not any(value) for value in credential.buffers.values()))
        self.assertFalse(any(oauth.token))

    async def test_credential_failure_closes_unused_oauth_backend(self):
        credential = CredentialMemoryBackend(error=RuntimeError("fixture"))
        oauth = OAuthMemoryBackend()
        calls = 0

        async def operation(_settings, _token):
            nonlocal calls
            calls += 1

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential, oauth_backend=oauth, operation=operation
        )

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(
            result.protected_failure_category,
            "protected_source_open_failed",
        )
        self.assertEqual((result.settings_load_calls, result.oauth_load_calls), (0, 0))
        self.assertEqual(calls, 0)
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertTrue(result.private_resources_closed)

    async def test_precise_source_failure_category_propagates_without_detail(self):
        credential = CredentialMemoryBackend(
            error=ProtectedSourceOpenFailure(
                "protected_source_record_unavailable"
            )
        )
        oauth = OAuthMemoryBackend()

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential,
            oauth_backend=oauth,
            operation=lambda _settings, _token: None,
        )

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(
            result.protected_failure_category,
            "protected_source_record_unavailable",
        )
        self.assertEqual((result.oauth_load_calls, oauth.load_calls), (0, 0))

    async def test_degraded_settings_stop_before_oauth_load(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend()

        def degraded_loader(_environment):
            return load_settings({"NIA_BITRIX_MODE": "active"})

        async def operation(_settings, _token):
            raise AssertionError("must-not-run")

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential,
            oauth_backend=oauth,
            operation=operation,
            settings_loader=degraded_loader,
        )

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(
            result.protected_failure_category,
            "protected_settings_validation_failed",
        )
        self.assertEqual((result.settings_load_calls, result.oauth_load_calls), (0, 0))
        self.assertEqual(oauth.close_calls, 1)
        self.assertTrue(result.private_resources_closed)

    async def test_refresh_capable_backend_is_rejected_without_load(self):
        credential = CredentialMemoryBackend()
        oauth = RefreshCapableOAuthBackend()

        async def operation(_settings, _token):
            raise AssertionError("must-not-run")

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential, oauth_backend=oauth, operation=operation
        )

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(result.protected_failure_category, "oauth_load_failed")
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (0, 0))
        self.assertEqual((oauth.load_calls, oauth.close_calls), (0, 1))
        self.assertTrue(result.private_resources_closed)

    async def test_invalid_oauth_record_or_token_fails_closed(self):
        variants = (
            object(),
            InjectedStoredOAuthRecord(access_token=bytearray()),
            InjectedStoredOAuthRecord(access_token=bytearray(b"bad\x00token")),
        )
        for record in variants:
            with self.subTest(record_type=type(record).__name__):
                credential = CredentialMemoryBackend()
                oauth = OAuthMemoryBackend(record=record)
                result = await execute_m82_injected_settings_oauth_once(
                    credential_backend=credential,
                    oauth_backend=oauth,
                    operation=lambda _settings, _token: None,
                )
                self.assertEqual(result.status, M82Status.NO_GO)
                self.assertEqual(
                    result.protected_failure_category,
                    "oauth_load_failed",
                )
                self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
                self.assertTrue(result.private_resources_closed)

    async def test_oauth_load_cancellation_is_terminal_and_closed(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend(error=asyncio.CancelledError())

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential,
            oauth_backend=oauth,
            operation=lambda _settings, _token: None,
        )

        self.assertEqual(result.status, M82Status.CANCELLED)
        self.assertEqual(result.protected_failure_category, "cancelled")
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (1, 0))
        self.assertTrue(result.private_resources_closed)

    async def test_operation_cancellation_zeroizes_and_closes_both_owners(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend()

        async def operation(_settings, _token):
            raise asyncio.CancelledError()

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential, oauth_backend=oauth, operation=operation
        )

        self.assertEqual(result.status, M82Status.CANCELLED)
        self.assertEqual(result.protected_failure_category, "cancelled")
        self.assertTrue(result.private_resources_closed)
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertFalse(any(oauth.token))

    async def test_oauth_close_failure_overrides_success(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend(close_error=RuntimeError("fixture-close"))

        async def operation(_settings, _token):
            return None

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential, oauth_backend=oauth, operation=operation
        )

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(
            result.protected_failure_category,
            "protected_resources_close_failed",
        )
        self.assertFalse(result.oauth_close_verified)
        self.assertFalse(result.private_resources_closed)
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (1, 0))

    async def test_lifecycle_operation_failure_has_closed_public_category(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend()

        async def operation(_settings, _token):
            raise RuntimeError("private-lifecycle-detail")

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential,
            oauth_backend=oauth,
            operation=operation,
        )

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(
            result.protected_failure_category,
            "lifecycle_operation_failed",
        )
        self.assertNotIn("private-lifecycle-detail", repr(result))

    async def test_oauth_owner_reuse_never_loads_again(self):
        oauth = OAuthMemoryBackend()
        owner = StoredOAuthNoRefreshResourceOwner(backend=oauth)
        settings = load_settings(
            {name: value.decode() for name, value in credential_buffers().items()}
        )

        async def operation(token):
            token.read_text()

        first = await owner.run_once(settings=settings, operation=operation)
        second = await owner.run_once(settings=settings, operation=operation)

        self.assertEqual(first.status, M82Status.READY)
        self.assertEqual(second.reason, "m82_oauth_owner_reuse_rejected")
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))

    async def test_snapshot_and_source_are_redacted_and_have_no_real_access(self):
        credential = CredentialMemoryBackend()
        oauth = OAuthMemoryBackend()

        async def operation(_settings, _token):
            raise RuntimeError("fixture-private-detail")

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = await execute_m82_injected_settings_oauth_once(
                credential_backend=credential,
                oauth_backend=oauth,
                operation=operation,
            )
        rendered = repr(asdict(result)) + output.getvalue()
        self.assertNotIn("fixture-oauth-token", rendered)
        self.assertNotIn("fixture-private-detail", rendered)
        self.assertFalse(result.first_confirmation_request_ready)
        self.assertFalse(result.attention_required_now)
        self.assertFalse(result.source_bound)
        self.assertFalse(result.command_available)
        self.assertEqual(result.external_calls, 0)
        self.assertTrue(result.connector_locked_off)

        module_source = (ROOT / "bitrix_connector" / "bitrix_history_r0_m82_injected_settings_oauth_owner.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "win32cred", "keyring", "ctypes", "httpx", "pymongo", "motor",
            "dotenv", "os.environ", "refresh_access_token(", "argparse", "input(",
            "subprocess", "socket", "print(", "toast", "messagebox",
        ):
            self.assertNotIn(forbidden, module_source)


if __name__ == "__main__":
    unittest.main()
