import asyncio
import unittest
from dataclasses import dataclass
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthRecord,
)
from bitrix_connector.bitrix_history_r0_m86_protected_lifecycle_resources import (
    M86ProtectedLifecycleResourceOwner,
    build_real_m86_protected_lifecycle_resource_owner,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]


def credential_buffers():
    values = (
        "fixture-m86h.invalid",
        "fixture-member",
        "fixture-client",
        "fixture-client-secret",
        "mongodb://fixture-m86h.invalid",
        "fixture-db",
        "fixture-installations",
    )
    return {
        name: bytearray(value.encode("utf-8"))
        for name, value in zip(PROTECTED_SETTING_NAMES, values, strict=True)
    }


class CredentialBackend:
    def __init__(self, *, close_error=None):
        self.buffers = credential_buffers()
        self.record = InjectedWindowsCredentialRecord(
            target_id=M80_CREDENTIAL_TARGET_ID,
            buffers=self.buffers,
        )
        self.fetch_calls = 0
        self.close_calls = 0
        self.close_error = close_error

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        if target_id != M80_CREDENTIAL_TARGET_ID:
            raise RuntimeError("fixture_target_invalid")
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()
        if self.close_error is not None:
            raise self.close_error


class OAuthBackend:
    def __init__(self, *, close_error=None):
        self.token = bytearray(b"fixture-m86h-oauth")
        self.record = InjectedStoredOAuthRecord(access_token=self.token)
        self.load_calls = 0
        self.close_calls = 0
        self.close_error = close_error

    async def load_stored_once(self, _settings):
        self.load_calls += 1
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()
        if self.close_error is not None:
            raise self.close_error


class RefreshCapableOAuthBackend(OAuthBackend):
    async def refresh_access_token(self):
        raise AssertionError("must-not-run")


class Outcome:
    def require_anchor(self):
        return object()


@dataclass(frozen=True)
class M88Result:
    state: str


class Operations:
    def __init__(self, *, result_state="VERIFIED", cancel=False, slow=False):
        self.result_state = result_state
        self.cancel = cancel
        self.slow = slow
        self.outcome = Outcome()
        self.identities = []
        self.token_view = None
        self.calls = []

    async def preflight(self, settings, token_view):
        self.calls.append("preflight")
        self.identities.append((id(settings), id(token_view), id(self.outcome)))
        self.token_view = token_view
        self.assert_token = token_view.read_text()
        return self.outcome

    async def cross_turn(self, settings, token_view, outcome):
        self.calls.append("cross_turn")
        self.identities.append((id(settings), id(token_view), id(outcome)))
        if self.cancel:
            raise asyncio.CancelledError()
        if self.slow:
            await asyncio.sleep(1)

    async def m88(self, settings, token_view, outcome):
        self.calls.append("m88")
        self.identities.append((id(settings), id(token_view), id(outcome)))
        token_view.read_text()
        return M88Result(self.result_state)


def owner(*, credential=None, oauth=None, operations=None, enabled=True, lifetime=300):
    credential = credential or CredentialBackend()
    oauth = oauth or OAuthBackend()
    operations = operations or Operations()
    value = M86ProtectedLifecycleResourceOwner(
        credential_backend=credential,
        oauth_backend=oauth,
        preflight_operation=operations.preflight,
        cross_turn_operation=operations.cross_turn,
        m88_operation=operations.m88,
        execution_enabled=enabled,
        lifetime_seconds=lifetime,
    )
    return value, credential, oauth, operations


class M86ProtectedLifecycleResourceOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_load_same_views_and_outcome_span_preflight_wait_and_m88(self):
        value, credential, oauth, operations = owner()

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertEqual(snapshot.protected_failure_category, "none")
        self.assertEqual(operations.calls, ["preflight", "cross_turn", "m88"])
        self.assertEqual(len(set(operations.identities)), 1)
        self.assertTrue(snapshot.same_settings_view_used)
        self.assertTrue(snapshot.same_oauth_view_used)
        self.assertTrue(snapshot.same_private_outcome_used)
        self.assertFalse(snapshot.private_outcome_persisted)
        self.assertEqual(snapshot.credential_source_read_calls, 7)
        self.assertEqual(snapshot.settings_load_calls, 1)
        self.assertEqual((snapshot.oauth_load_calls, snapshot.oauth_refresh_calls), (1, 0))
        self.assertEqual(snapshot.oauth_token_view_reads, 2)
        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
        self.assertTrue(snapshot.private_resources_closed)
        self.assertTrue(all(not any(item) for item in credential.buffers.values()))
        self.assertFalse(any(oauth.token))
        with self.assertRaisesRegex(RuntimeError, "oauth_view_closed"):
            operations.token_view.read_text()

    async def test_rolled_back_result_is_accepted_and_resources_close(self):
        operations = Operations(result_state="ROLLED-BACK")
        value, credential, oauth, _ = owner(operations=operations)

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "ROLLED-BACK")
        self.assertEqual(snapshot.protected_failure_category, "none")
        self.assertEqual(snapshot.reason, "m86h_protected_lifecycle_rolled_back")
        self.assertTrue(snapshot.private_resources_closed)
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))

    async def test_preview_and_disabled_owner_open_nothing(self):
        value, credential, oauth, operations = owner(enabled=False)

        preview = await value.run_once()
        blocked = await value.run_once(execute=True)

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(blocked.reason, "m86h_execution_not_enabled")
        self.assertEqual((credential.fetch_calls, oauth.load_calls), (0, 0))
        self.assertEqual(operations.calls, [])

    async def test_refresh_capable_backend_is_rejected_before_load(self):
        oauth = RefreshCapableOAuthBackend()
        value, credential, _, operations = owner(oauth=oauth)

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.protected_failure_category, "oauth_load_failed")
        self.assertEqual(oauth.load_calls, 0)
        self.assertEqual(oauth.close_calls, 1)
        self.assertEqual(operations.calls, [])
        self.assertTrue(snapshot.private_resources_closed)

    async def test_degraded_settings_stop_before_oauth_and_operations(self):
        value, credential, oauth, operations = owner()
        value._settings_loader = lambda _environment: load_settings(
            {"NIA_BITRIX_MODE": "active"}
        )

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.protected_failure_category,
            "protected_settings_validation_failed",
        )
        self.assertEqual(oauth.load_calls, 0)
        self.assertEqual(operations.calls, [])
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))

    async def test_cross_turn_cancellation_is_terminal_and_zeroizes(self):
        operations = Operations(cancel=True)
        value, credential, oauth, _ = owner(operations=operations)

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertEqual(snapshot.protected_failure_category, "cancelled")
        self.assertEqual(snapshot.retry_budget, 0)
        self.assertEqual(operations.calls, ["preflight", "cross_turn"])
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertFalse(any(oauth.token))

    async def test_lifetime_timeout_cancels_scope_and_closes_resources(self):
        operations = Operations(slow=True)
        value, credential, oauth, _ = owner(
            operations=operations,
            lifetime=0.01,
        )

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "TIMED-OUT")
        self.assertEqual(snapshot.protected_failure_category, "cancelled")
        self.assertTrue(snapshot.private_resources_closed)
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertFalse(any(oauth.token))

    async def test_invalid_m88_result_is_no_go_after_single_load_and_cleanup(self):
        operations = Operations(result_state="UNKNOWN")
        value, credential, oauth, _ = owner(operations=operations)

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.protected_failure_category,
            "lifecycle_operation_failed",
        )
        self.assertEqual(snapshot.m88_calls, 1)
        self.assertEqual((snapshot.oauth_load_calls, snapshot.oauth_refresh_calls), (1, 0))
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertTrue(snapshot.private_resources_closed)

    async def test_oauth_close_failure_overrides_verified_lifecycle(self):
        oauth = OAuthBackend(close_error=RuntimeError("fixture-close"))
        value, credential, _, _ = owner(oauth=oauth)

        snapshot = await value.run_once(execute=True)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.protected_failure_category,
            "protected_resources_close_failed",
        )
        self.assertFalse(snapshot.oauth_close_verified)
        self.assertFalse(snapshot.private_resources_closed)
        self.assertEqual(credential.close_calls, 1)

    async def test_reuse_does_not_reload_resources(self):
        value, credential, oauth, _ = owner()
        first = await value.run_once(execute=True)
        second = await value.run_once(execute=True)

        self.assertEqual(first.state, "VERIFIED")
        self.assertEqual(second.reason, "m86h_resource_owner_reuse_rejected")
        self.assertEqual((credential.fetch_calls, oauth.load_calls), (1, 1))

    async def test_real_builder_preview_is_inert_and_opens_no_backend(self):
        value = build_real_m86_protected_lifecycle_resource_owner()
        credential = value._credential_backend
        oauth = value._oauth_backend

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertTrue(snapshot.protected_source_bound)
        self.assertEqual(snapshot.remaining_real_bindings, 2)
        self.assertIsNone(credential._native._api)
        self.assertIsNone(oauth._resources)

    def test_repr_and_source_expose_no_values_network_command_or_notification(self):
        value, *_ = owner()
        self.assertEqual(
            repr(value),
            "M86ProtectedLifecycleResourceOwner(<redacted>)",
        )
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_protected_lifecycle_resources.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "httpx",
            "mocktransport",
            "pymongo",
            "motor",
            "dotenv",
            "os.environ",
            "refresh_access_token(",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "lanzar_notificacion_codex",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
