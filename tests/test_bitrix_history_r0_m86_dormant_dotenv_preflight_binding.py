import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m86_dormant_dotenv_preflight_binding import (
    M86BJDormantBindingContract,
    M86BJFixturePreflightOwner,
    build_dormant_m86bj_binding,
)
from bitrix_connector.bitrix_history_r0_m86_stored_oauth_backend import (
    M86StoredOAuthBackend,
)
from bitrix_connector.bitrix_history_r0_protected_dotenv_source import (
    AllowlistedDotenvSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
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


class M86BJDormantDotenvPreflightBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_binding_preview_does_not_open_or_compose(self):
        with patch.object(
            AllowlistedDotenvSource,
            "open",
            new=AsyncMock(side_effect=AssertionError("must-not-open")),
        ) as open_mock:
            binding = build_dormant_m86bj_binding()
            result = binding.preview()
        open_mock.assert_not_awaited()
        self.assertEqual(result.state, "DORMANT-BOUND-NOT-EXECUTABLE")
        self.assertTrue(result.project_root_dotenv_bound)
        self.assertTrue(result.m86bi_backend_bound)
        self.assertTrue(result.m86c_owner_bound)
        self.assertFalse(result.path_checked)
        self.assertFalse(result.path_opened)
        self.assertFalse(result.execution_surface_available)
        self.assertEqual(
            (
                result.source_factory_calls,
                result.oauth_factory_calls,
                result.http_factory_calls,
                result.real_open_budget,
                result.external_calls,
            ),
            (0, 0, 0, 0, 0),
        )
        self.assertFalse(hasattr(binding, "run_once"))
        self.assertFalse(hasattr(binding, "build_owner"))
        self.assertEqual(binding._dotenv_path.parent, ROOT)
        self.assertEqual(binding._dotenv_path.name, ".env")

    async def test_fixture_owner_reaches_verified_with_doubles(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bj-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            http_factory = HermeticPreflightHttpFactory()
            owner = M86BJFixturePreflightOwner(
                source=AllowlistedDotenvSource(path),
                oauth_backend=M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=http_factory,
            )
            result = await owner.run_once()
        self.assertEqual(result.state, "VERIFIED")
        self.assertTrue(result.combined_preflight_verified)
        self.assertTrue(result.private_resources_closed)
        self.assertEqual(result.credential_source_read_calls, 7)
        self.assertEqual((result.oauth_load_calls, result.oauth_refresh_calls), (1, 0))
        self.assertEqual(result.http_client_factory_calls, 2)
        self.assertEqual(len(http_factory.requests), 4)
        self.assertEqual((result.history_read_calls, result.messages_sent), (0, 0))

    async def test_missing_fixture_value_stops_before_oauth_and_http(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bj-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload(omit=PROTECTED_SETTING_NAMES[-1]))
            oauth_factory = OAuthFactoryFixture()
            http_factory = HermeticPreflightHttpFactory()
            owner = M86BJFixturePreflightOwner(
                source=AllowlistedDotenvSource(path),
                oauth_backend=M86StoredOAuthBackend(resources_factory=oauth_factory),
                http_client_factory=http_factory,
            )
            result = await owner.run_once()
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual((result.oauth_load_calls, result.http_client_factory_calls), (0, 0))
        self.assertEqual(http_factory.requests, [])

    async def test_fixture_owner_is_one_shot(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bj-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            owner = M86BJFixturePreflightOwner(
                source=AllowlistedDotenvSource(path),
                oauth_backend=M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=HermeticPreflightHttpFactory(),
            )
            await owner.run_once()
            with self.assertRaisesRegex(RuntimeError, "fixture_owner_reused"):
                await owner.run_once()

    def test_contract_and_real_binding_expose_no_execution(self):
        contract = M86BJDormantBindingContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BJ", "DORMANT-BOUND-NOT-EXECUTABLE"))
        self.assertTrue(contract.exact_project_root_path)
        self.assertFalse(contract.real_binding_has_execute)
        self.assertFalse(contract.real_binding_has_cli)
        self.assertTrue(contract.fixture_owner_separate)
        self.assertEqual(
            (contract.real_open_budget, contract.oauth_budget, contract.network_budget),
            (0, 0, 0),
        )
        self.assertEqual(repr(build_dormant_m86bj_binding()), "M86BJDormantDotenvPreflightBinding(<redacted>)")

    def test_module_has_no_real_command_or_service_entrypoint(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_dormant_dotenv_preflight_binding.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "argparse",
            "input(",
            "subprocess",
            "uvicorn",
            "fastapi",
            "credwrite",
            "creddelete",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
