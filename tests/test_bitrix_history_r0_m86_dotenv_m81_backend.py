import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m86_combined_preflight_owner import (
    M86CombinedPreflightOwner,
)
from bitrix_connector.bitrix_history_r0_m86_dotenv_m81_backend import (
    M86BIDotenvM81BackendContract,
    M86BIInjectedDotenvCredentialBackend,
)
from bitrix_connector.bitrix_history_r0_m86_stored_oauth_backend import (
    M86StoredOAuthBackend,
)
from bitrix_connector.bitrix_history_r0_protected_dotenv_source import (
    AllowlistedDotenvSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)
from tests.test_bitrix_history_r0_m86_combined_preflight_owner import (
    HermeticPreflightHttpFactory,
    OAuthFactoryFixture,
)


ROOT = Path(__file__).resolve().parents[1]
VALUES = (
    "bitrix.fixture.invalid",
    "fixture-member",
    "fixture-client",
    "fixture-client-secret",
    "mongodb://fixture.invalid",
    "fixture-db",
    "fixture-installations",
)


def fixture_payload(*, omit=None):
    return b"\n".join(
        name.encode("ascii") + b"=" + value.encode("utf-8")
        for name, value in zip(PROTECTED_SETTING_NAMES, VALUES, strict=True)
        if name != omit
    ) + b"\n"


class M86BIDotenvM81BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_injected_fixture_reaches_m81_record_once(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bi-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            backend = M86BIInjectedDotenvCredentialBackend(
                source=AllowlistedDotenvSource(path)
            )
            record = await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
            buffers = record.take_buffers_once()
            self.assertEqual(tuple(buffers), PROTECTED_SETTING_NAMES)
            self.assertTrue(all(type(value) is bytearray for value in buffers.values()))
            for value in buffers.values():
                value[:] = b"\x00" * len(value)
            buffers.clear()
            await backend.close()
        self.assertEqual(
            (
                backend.fetch_calls,
                backend.source_open_calls,
                backend.source_read_calls,
                backend.source_close_calls,
                backend.backend_close_calls,
            ),
            (1, 1, 7, 1, 1),
        )

    async def test_fixture_backend_runs_m82_and_m86c_with_only_doubles(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bi-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            backend = M86BIInjectedDotenvCredentialBackend(
                source=AllowlistedDotenvSource(path)
            )
            oauth_factory = OAuthFactoryFixture()
            oauth = M86StoredOAuthBackend(resources_factory=oauth_factory)
            http_factory = HermeticPreflightHttpFactory()
            owner = M86CombinedPreflightOwner(
                credential_backend=backend,
                oauth_backend=oauth,
                http_client_factory=http_factory,
                hermetic_execution=True,
            )
            result = await owner.run_once()
            owner.take_history_outcome_once()
        self.assertEqual(result.state, "VERIFIED")
        self.assertTrue(result.combined_preflight_verified)
        self.assertTrue(result.private_resources_closed)
        self.assertEqual(result.credential_source_read_calls, 7)
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (1, 0))
        self.assertEqual(
            (result.bot_read_calls, result.openline_read_calls, result.history_dialog_read_calls),
            (2, 1, 1),
        )
        self.assertEqual(result.history_read_calls, 0)
        self.assertEqual(len(http_factory.requests), 4)
        self.assertTrue(all(client.is_closed for client in http_factory.clients))
        self.assertEqual(backend.backend_close_calls, 1)

    async def test_missing_fixture_value_stops_before_oauth_and_http(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bi-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload(omit=PROTECTED_SETTING_NAMES[-1]))
            backend = M86BIInjectedDotenvCredentialBackend(
                source=AllowlistedDotenvSource(path)
            )
            oauth_factory = OAuthFactoryFixture()
            oauth = M86StoredOAuthBackend(resources_factory=oauth_factory)
            http_factory = HermeticPreflightHttpFactory()
            result = await M86CombinedPreflightOwner(
                credential_backend=backend,
                oauth_backend=oauth,
                http_client_factory=http_factory,
                hermetic_execution=True,
            ).run_once()
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual((result.oauth_load_calls, result.http_client_factory_calls), (0, 0))
        self.assertEqual(http_factory.requests, [])
        self.assertEqual((backend.source_close_calls, backend.backend_close_calls), (1, 1))

    async def test_wrong_target_does_not_open_injected_source(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bi-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            backend = M86BIInjectedDotenvCredentialBackend(
                source=AllowlistedDotenvSource(path)
            )
            open_mock = AsyncMock()
            with patch.object(AllowlistedDotenvSource, "open", new=open_mock):
                with self.assertRaises(ProtectedSourceOpenFailure):
                    await backend.fetch_exact("wrong-target")
            open_mock.assert_not_awaited()
            await backend.close()
        self.assertEqual(backend.source_open_calls, 0)

    async def test_source_cleanup_failure_is_terminal(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bi-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            backend = M86BIInjectedDotenvCredentialBackend(
                source=AllowlistedDotenvSource(path)
            )
            with patch.object(
                AllowlistedDotenvSource,
                "close",
                new=AsyncMock(side_effect=RuntimeError("fixture-cleanup")),
            ):
                with self.assertRaisesRegex(RuntimeError, "source_cleanup_failed"):
                    await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
        self.assertEqual(backend.source_close_calls, 1)

    async def test_backend_is_one_shot(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bi-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            backend = M86BIInjectedDotenvCredentialBackend(
                source=AllowlistedDotenvSource(path)
            )
            record = await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
            record.clear()
            with self.assertRaises(ProtectedSourceOpenFailure):
                await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
            await backend.close()
        self.assertEqual(backend.fetch_calls, 1)

    def test_contract_and_module_have_no_real_route_or_writer(self):
        contract = M86BIDotenvM81BackendContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BI", "FIXTURE-ONLY-INERT"))
        self.assertTrue(contract.source_must_be_injected)
        self.assertTrue(contract.exact_target_only)
        self.assertEqual((contract.exact_name_budget, contract.source_open_budget), (7, 1))
        self.assertTrue(contract.direct_bytearray_transfer)
        self.assertFalse(contract.real_path_factory_present)
        self.assertEqual((contract.credential_write_budget, contract.fallback_budget), (0, 0))
        self.assertFalse(contract.cli_available)
        self.assertFalse(contract.real_execution_authorized)
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_m86_dotenv_m81_backend.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            'path(".env")',
            "path('.env')",
            "credwrite",
            "creddelete",
            "os.environ",
            "getenv",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
