import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    M82Status,
    StoredOAuthNoRefreshResourceOwner,
    execute_m82_injected_settings_oauth_once,
)
from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_MAGIC,
    WindowsCredentialManagerBackend,
)
from bitrix_connector.bitrix_history_r0_m86_stored_oauth_backend import (
    M86StoredOAuthBackend,
    M86_STORED_OAUTH_TIMEOUT_SECONDS,
    build_real_m86_stored_oauth_backend,
    inspect_m86_stored_oauth_binding,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)
from bitrix_connector.pilot_discovery_factory import PilotDiscoveryOAuthFactory


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-m86-stored-token"


def protected_blob():
    values = (
        "bitrix.fixture.invalid",
        "fixture-member",
        "fixture-client",
        "fixture-client-secret",
        "mongodb://fixture.invalid",
        "fixture-db",
        "fixture-installations",
    )
    blob = bytearray(M84_BLOB_MAGIC)
    for name, text in zip(PROTECTED_SETTING_NAMES, values, strict=True):
        encoded_name = name.encode("ascii")
        encoded_value = text.encode("utf-8")
        blob.extend(len(encoded_name).to_bytes(2, "big"))
        blob.extend(encoded_name)
        blob.extend(len(encoded_value).to_bytes(4, "big"))
        blob.extend(encoded_value)
    return blob


class CredentialNativeFixture:
    def __init__(self):
        self.blob = protected_blob()
        self.read_calls = 0
        self.close_calls = 0

    async def read_generic_blob_once(self, target_id):
        self.read_calls += 1
        if target_id != M80_CREDENTIAL_TARGET_ID:
            raise AssertionError("unexpected target")
        blob, self.blob = self.blob, bytearray()
        return blob

    async def close(self):
        self.close_calls += 1
        self.blob[:] = b"\x00" * len(self.blob)


class ProviderFixture:
    def __init__(self, *, token=TOKEN, error=None):
        self.token = token
        self.error = error
        self.get_calls = []
        self.refresh_calls = 0

    async def get_access_token(self, member_id):
        self.get_calls.append(member_id)
        if self.error is not None:
            raise self.error
        return self.token

    async def refresh_access_token(self, *_args):
        self.refresh_calls += 1
        raise AssertionError("refresh must never run")


class ResourcesFixture:
    def __init__(self, *, provider=None, close_error=None):
        self.oauth_provider = provider or ProviderFixture()
        self.member_id = "fixture-member"
        self.close_error = close_error
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class FactoryFixture:
    def __init__(self, resources=None, *, error=None):
        self.resources = resources or ResourcesFixture()
        self.error = error
        self.calls = []

    async def build(self, settings, *, timeout_seconds):
        self.calls.append((settings, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.resources


class M86StoredOAuthBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_m84_and_m82_use_real_ready_adapter_with_one_load_no_refresh(self):
        native = CredentialNativeFixture()
        credential = WindowsCredentialManagerBackend(native=native)
        resources = ResourcesFixture()
        factory = FactoryFixture(resources)
        oauth = M86StoredOAuthBackend(resources_factory=factory)
        observed = []

        async def operation(settings, token_view):
            observed.append((settings.bitrix_member_id, token_view.read_text()))

        result = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential,
            oauth_backend=oauth,
            operation=operation,
        )

        self.assertEqual(result.status, M82Status.READY)
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (1, 0))
        self.assertEqual((oauth.load_calls, oauth.token_read_calls, oauth.close_calls), (1, 1, 1))
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(factory.calls[0][1], M86_STORED_OAUTH_TIMEOUT_SECONDS)
        self.assertEqual(resources.oauth_provider.get_calls, [resources.member_id])
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(resources.close_calls, 1)
        self.assertEqual((native.read_calls, native.close_calls), (1, 1))
        self.assertEqual(observed, [("fixture-member", TOKEN)])

    async def test_backend_is_terminal_and_never_retries_factory_or_token_read(self):
        resources = ResourcesFixture(provider=ProviderFixture(error=RuntimeError("private")))
        factory = FactoryFixture(resources)
        backend = M86StoredOAuthBackend(resources_factory=factory)

        with self.assertRaisesRegex(RuntimeError, "private"):
            await backend.load_stored_once(object())
        with self.assertRaisesRegex(RuntimeError, "reuse_rejected"):
            await backend.load_stored_once(object())
        await backend.close()

        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(len(resources.oauth_provider.get_calls), 1)
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(resources.close_calls, 1)
        self.assertEqual(backend.close_calls, 1)

    async def test_factory_failure_is_terminal_with_zero_retry_and_zero_token_read(self):
        factory = FactoryFixture(error=RuntimeError("private build"))
        backend = M86StoredOAuthBackend(resources_factory=factory)

        with self.assertRaisesRegex(RuntimeError, "private build"):
            await backend.load_stored_once(object())
        await backend.close()

        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(backend.token_read_calls, 0)
        self.assertEqual(backend.close_calls, 1)

    async def test_cancellation_closes_built_resources_and_remains_terminal(self):
        resources = ResourcesFixture(provider=ProviderFixture(error=asyncio.CancelledError()))
        backend = M86StoredOAuthBackend(resources_factory=FactoryFixture(resources))

        with self.assertRaises(asyncio.CancelledError):
            await backend.load_stored_once(object())
        await backend.close()

        self.assertEqual(resources.close_calls, 1)
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(backend.close_calls, 1)

    async def test_invalid_token_fails_closed_and_is_not_retried(self):
        for token in ("", "bad\x00token", "x" * (8 * 1024 + 1), object()):
            with self.subTest(token_type=type(token).__name__):
                resources = ResourcesFixture(provider=ProviderFixture(token=token))
                factory = FactoryFixture(resources)
                backend = M86StoredOAuthBackend(resources_factory=factory)
                with self.assertRaises((TypeError, ValueError)):
                    await backend.load_stored_once(object())
                await backend.close()
                self.assertEqual((len(factory.calls), resources.close_calls), (1, 1))
                self.assertEqual(resources.oauth_provider.refresh_calls, 0)

    async def test_close_failure_is_visible_to_m82_owner(self):
        resources = ResourcesFixture(close_error=RuntimeError("private close"))
        backend = M86StoredOAuthBackend(resources_factory=FactoryFixture(resources))
        owner = StoredOAuthNoRefreshResourceOwner(backend=backend)

        async def operation(_view):
            return None

        result = await owner.run_once(settings=object(), operation=operation)

        self.assertEqual(result.status, M82Status.NO_GO)
        self.assertEqual(result.reason, "m82_oauth_owner_close_failed")
        self.assertEqual(resources.close_calls, 1)
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)

    def test_real_binding_is_lazy_and_reports_no_real_open(self):
        backend = build_real_m86_stored_oauth_backend()
        self.assertIsInstance(backend, M86StoredOAuthBackend)
        self.assertIsInstance(backend._factory, PilotDiscoveryOAuthFactory)
        self.assertEqual((backend.load_calls, backend.token_read_calls, backend.close_calls), (0, 0, 0))

        snapshot = inspect_m86_stored_oauth_binding()
        self.assertEqual((snapshot.phase, snapshot.state), ("M86-A", "BOUND-NOT-OPENED"))
        self.assertEqual((snapshot.stored_load_budget, snapshot.refresh_budget, snapshot.retry_budget), (1, 0, 0))
        self.assertEqual((snapshot.real_resource_builds, snapshot.real_token_reads), (0, 0))
        self.assertEqual(snapshot.remaining_real_bindings, 4)
        self.assertFalse(snapshot.source_opened)
        self.assertFalse(snapshot.command_available)
        self.assertFalse(snapshot.attention_required_now)

    def test_public_surface_has_no_refresh_and_source_has_no_execution_channel(self):
        backend = M86StoredOAuthBackend(resources_factory=FactoryFixture())
        self.assertFalse(hasattr(backend, "refresh"))
        self.assertFalse(hasattr(backend, "refresh_access_token"))
        self.assertEqual(repr(backend), "M86StoredOAuthBackend(<redacted>)")
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_stored_oauth_backend.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "dotenv",
            "os.environ",
            "credentialmanagerbackend",
            "httpx.asyncclient",
            "mocktransport",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "toast",
            "messagebox",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
