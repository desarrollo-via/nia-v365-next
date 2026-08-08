import asyncio
import unittest
from pathlib import Path

import httpx

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthRecord,
)
from bitrix_connector.bitrix_history_r0_m83_injected_https_owner import (
    M83InjectedHttpsOwner,
    M83Status,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]
TOKEN = b"fixture-m83-private-token"


def credential_buffers(*, domain="bitrix.fixture.invalid"):
    values = (
        domain,
        "fixture-member",
        "fixture-client",
        "fixture-client-secret",
        "mongodb://fixture.invalid",
        "fixture-db",
        "fixture-installations",
    )
    return {
        name: bytearray(value.encode())
        for name, value in zip(PROTECTED_SETTING_NAMES, values, strict=True)
    }


class CredentialBackend:
    def __init__(self, *, domain="bitrix.fixture.invalid", error=None):
        self.buffers = credential_buffers(domain=domain)
        self.record = InjectedWindowsCredentialRecord(
            target_id=M80_CREDENTIAL_TARGET_ID,
            buffers=self.buffers,
        )
        self.error = error
        self.fetch_calls = 0
        self.close_calls = 0

    async def fetch_exact(self, _target_id):
        self.fetch_calls += 1
        if self.error is not None:
            raise self.error
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()


class OAuthBackend:
    def __init__(self, *, error=None):
        self.token = bytearray(TOKEN)
        self.record = InjectedStoredOAuthRecord(access_token=self.token)
        self.error = error
        self.load_calls = 0
        self.close_calls = 0

    async def load_stored_once(self, _settings):
        self.load_calls += 1
        if self.error is not None:
            raise self.error
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()


class MockFactory:
    def __init__(
        self,
        *,
        cancel_name=None,
        fail_name=None,
        wait_name=None,
        wrong_type=False,
    ):
        self.cancel_name = cancel_name
        self.fail_name = fail_name
        self.wait_name = wait_name
        self.wrong_type = wrong_type
        self.calls = []
        self.requests = []

    def __call__(self, name):
        self.calls.append(name)
        if self.cancel_name == name:
            raise asyncio.CancelledError()
        if self.fail_name == name:
            raise RuntimeError("private fixture transport failure")
        if self.wrong_type:
            return object()

        async def handler(request):
            self.requests.append(request)
            if self.wait_name == name:
                await asyncio.Future()
            return httpx.Response(500, json={"fixture": True})

        return httpx.MockTransport(handler)


def owner(*, credential=None, oauth=None, factory=None, nia_url=None):
    credential = credential or CredentialBackend()
    oauth = oauth or OAuthBackend()
    factory = factory or MockFactory()
    value = M83InjectedHttpsOwner(
        credential_backend=credential,
        oauth_backend=oauth,
        nia_base_url=nia_url or "https://nia.fixture.invalid",
        mock_transport_factory=factory,
    )
    return value, credential, oauth, factory


class M83InjectedHttpsOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_m82_builds_four_concrete_https_clients_once_under_mock_transport(self):
        value, credential, oauth, factory = owner()

        self.assertEqual(factory.calls, [])
        result = await value.run_once()

        self.assertEqual(result.status, M83Status.VERIFIED)
        self.assertEqual(result.credential_source_read_calls, 7)
        self.assertEqual((result.settings_load_calls, result.oauth_load_calls), (1, 1))
        self.assertEqual((result.oauth_refresh_calls, result.oauth_token_view_reads), (0, 1))
        self.assertEqual(result.binding_oauth_loader_calls, 1)
        self.assertEqual(result.binding_oauth_close_calls, 1)
        self.assertEqual(result.http_resource_factory_calls, 4)
        self.assertEqual(result.concrete_builder_calls, 4)
        self.assertEqual((result.dependency_close_calls, result.http_close_calls), (4, 4))
        self.assertEqual(factory.calls, ["nia", "bitrix", "deleter", "history"])
        self.assertEqual(factory.requests, [])
        self.assertTrue(result.https_origins_verified)
        self.assertTrue(result.same_private_token_shared)
        self.assertTrue(result.all_private_resources_closed)
        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
        self.assertTrue(all(not any(item) for item in credential.buffers.values()))
        self.assertFalse(any(oauth.token))

    async def test_owner_reuse_is_rejected_without_second_source_or_factory_call(self):
        value, credential, oauth, factory = owner()

        first = await value.run_once()
        second = await value.run_once()

        self.assertEqual(first.status, M83Status.VERIFIED)
        self.assertEqual(second.reason, "m83_owner_reuse_rejected")
        self.assertEqual(second.owner_run_calls, 0)
        self.assertEqual((credential.fetch_calls, oauth.load_calls), (1, 1))
        self.assertEqual(len(factory.calls), 4)

    async def test_credential_failure_stops_before_oauth_and_clients(self):
        value, credential, oauth, factory = owner(
            credential=CredentialBackend(error=RuntimeError("private fixture"))
        )

        result = await value.run_once()

        self.assertEqual(result.status, M83Status.NO_GO)
        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual((oauth.load_calls, oauth.close_calls), (0, 1))
        self.assertEqual(factory.calls, [])
        self.assertTrue(result.all_private_resources_closed)

    async def test_oauth_failure_stops_before_clients_without_refresh_or_retry(self):
        value, _, oauth, factory = owner(
            oauth=OAuthBackend(error=RuntimeError("private fixture"))
        )

        result = await value.run_once()

        self.assertEqual(result.status, M83Status.NO_GO)
        self.assertEqual((oauth.load_calls, oauth.close_calls), (1, 1))
        self.assertEqual(result.oauth_refresh_calls, 0)
        self.assertEqual(result.retry_budget, 0)
        self.assertEqual(factory.calls, [])

    async def test_factory_failure_is_terminal_and_closes_every_created_resource(self):
        value, _, _, factory = owner(factory=MockFactory(fail_name="deleter"))

        result = await value.run_once()

        self.assertEqual(result.status, M83Status.NO_GO)
        self.assertEqual(factory.calls, ["nia", "bitrix", "deleter"])
        self.assertEqual(result.http_resource_factory_calls, 3)
        self.assertEqual(result.dependency_close_calls, 2)
        self.assertEqual(result.http_close_calls, 2)
        self.assertTrue(result.all_private_resources_closed)

    async def test_non_mock_transport_is_rejected_before_client_construction(self):
        value, _, _, factory = owner(factory=MockFactory(wrong_type=True))

        result = await value.run_once()

        self.assertEqual(result.status, M83Status.NO_GO)
        self.assertEqual(factory.calls, ["nia"])
        self.assertEqual(result.concrete_builder_calls, 1)
        self.assertEqual(result.http_resource_factory_calls, 1)
        self.assertEqual((result.dependency_close_calls, result.http_close_calls), (0, 0))
        self.assertEqual(result.external_calls, 0)

    async def test_http_or_non_origin_inputs_are_rejected_before_any_source(self):
        for nia_url in (
            "http://nia.fixture.invalid",
            "https://user@nia.fixture.invalid",
            "https://nia.fixture.invalid/path",
        ):
            with self.subTest(nia_url=nia_url):
                with self.assertRaisesRegex(ValueError, "exact_https_origin_invalid"):
                    owner(nia_url=nia_url)

        value, credential, oauth, factory = owner(
            credential=CredentialBackend(domain="http://bitrix.fixture.invalid")
        )
        result = await value.run_once()
        self.assertEqual(result.status, M83Status.NO_GO)
        self.assertEqual((credential.fetch_calls, oauth.load_calls), (1, 1))
        self.assertEqual(factory.calls, [])

    async def test_cancellation_from_oauth_load_is_terminal_and_closed(self):
        value, credential, oauth, factory = owner(
            oauth=OAuthBackend(error=asyncio.CancelledError())
        )

        result = await value.run_once()

        self.assertEqual(result.status, M83Status.CANCELLED)
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertEqual(factory.calls, [])
        self.assertTrue(result.all_private_resources_closed)

    async def test_cancellation_during_third_factory_closes_prior_dependencies(self):
        value, credential, oauth, factory = owner(
            factory=MockFactory(cancel_name="deleter")
        )

        result = await value.run_once()

        self.assertEqual(result.status, M83Status.CANCELLED)
        self.assertEqual(factory.calls, ["nia", "bitrix", "deleter"])
        self.assertEqual((result.dependency_close_calls, result.http_close_calls), (2, 2))
        self.assertEqual((credential.close_calls, oauth.close_calls), (1, 1))
        self.assertTrue(result.all_private_resources_closed)

    def test_source_has_no_real_source_command_default_network_or_secret_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m83_injected_https_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env",
            "win32cred",
            "keyring",
            "pymongo",
            "motor",
            "dotenv",
            "os.environ",
            "refresh_access_token(",
            "asynchttptransport",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
