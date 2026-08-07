import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bitrix_connector.bitrix_history_r0_m86_dormant_real_dotenv_owner_factory import (
    M86BLDormantFactoryContract,
    M86BLFixtureOwnerFactory,
    build_dormant_m86bl_real_owner_factory,
)
from bitrix_connector.bitrix_history_r0_m86_dotenv_preflight_authorization_gate import (
    M86BK_AUTHORIZATION_LITERAL,
    M86BKFixtureAuthorizationGate,
)
from bitrix_connector.bitrix_history_r0_m86_stored_oauth_backend import (
    M86StoredOAuthBackend,
)
from bitrix_connector.bitrix_history_r0_protected_dotenv_source import (
    AllowlistedDotenvSource,
)
from tests.test_bitrix_history_r0_m86_combined_preflight_owner import (
    HermeticPreflightHttpFactory,
    OAuthFactoryFixture,
)
from tests.test_bitrix_history_r0_m86_dormant_dotenv_preflight_binding import (
    fixture_payload,
)


ROOT = Path(__file__).resolve().parents[1]


class M86BLDormantRealDotenvOwnerFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_binds_blueprint_without_construction_or_calls(self):
        factory = build_dormant_m86bl_real_owner_factory()
        result = factory.preview()
        self.assertEqual(result.state, "DORMANT-REAL-FACTORY-DISABLED")
        self.assertTrue(result.project_root_dotenv_bound)
        self.assertTrue(result.m86bi_backend_bound)
        self.assertTrue(result.stored_oauth_bound)
        self.assertTrue(result.m86c_owner_bound)
        self.assertTrue(result.real_factory_callable)
        self.assertFalse(result.real_execution_enabled)
        self.assertEqual(
            (
                result.factory_calls,
                result.source_constructions,
                result.source_open_calls,
                result.oauth_factory_calls,
                result.http_factory_calls,
                result.external_calls,
            ),
            (0, 0, 0, 0, 0, 0),
        )
        self.assertEqual(factory._dotenv_path.parent, ROOT)
        self.assertEqual(factory._dotenv_path.name, ".env")

    async def test_exact_gate_with_real_factory_stops_before_source_construction(self):
        factory = build_dormant_m86bl_real_owner_factory()
        gate = M86BKFixtureAuthorizationGate(owner_factory=factory)
        target = (
            "bitrix_connector.bitrix_history_r0_m86_dormant_real_dotenv_owner_factory."
            "AllowlistedDotenvSource"
        )
        with patch(target, side_effect=AssertionError("must-not-construct")) as source:
            result = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        source.assert_not_called()
        self.assertEqual(result.failure_category, "owner_factory_unavailable")
        self.assertTrue(result.authorization_consumed)
        self.assertEqual(factory.preview().factory_calls, 1)
        self.assertEqual(factory.preview().source_constructions, 0)

    async def test_fixture_factory_reaches_verified_behind_gate(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bl-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            http_factory = HermeticPreflightHttpFactory()
            fixture_factory = M86BLFixtureOwnerFactory(
                source_factory=lambda: AllowlistedDotenvSource(path),
                oauth_backend_factory=lambda: M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=http_factory,
            )
            result = await M86BKFixtureAuthorizationGate(
                owner_factory=fixture_factory
            ).run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("VERIFIED", "none"))
        self.assertEqual(fixture_factory.calls, 1)
        self.assertEqual(len(http_factory.requests), 4)
        self.assertFalse(result.real_path_bound)
        self.assertFalse(result.linked_to_real_execution)

    async def test_wrong_literal_does_not_call_fixture_factories(self):
        calls = []
        fixture_factory = M86BLFixtureOwnerFactory(
            source_factory=lambda: calls.append("source"),
            oauth_backend_factory=lambda: calls.append("oauth"),
            http_client_factory=lambda *_args: calls.append("http"),
        )
        result = await M86BKFixtureAuthorizationGate(
            owner_factory=fixture_factory
        ).run_once(confirm_code="sp")
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertEqual((fixture_factory.calls, calls), (0, []))

    def test_fixture_factory_is_one_shot(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bl-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            fixture_factory = M86BLFixtureOwnerFactory(
                source_factory=lambda: AllowlistedDotenvSource(path),
                oauth_backend_factory=lambda: M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=HermeticPreflightHttpFactory(),
            )
            fixture_factory()
            with self.assertRaisesRegex(RuntimeError, "fixture_factory_reused"):
                fixture_factory()

    def test_contract_and_module_have_no_cli_or_activation(self):
        contract = M86BLDormantFactoryContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BL", "DORMANT-REAL-FACTORY-DISABLED"))
        self.assertTrue(contract.exact_project_root_path)
        self.assertTrue(contract.real_factory_is_fail_closed)
        self.assertTrue(contract.fixture_factory_separate)
        self.assertEqual(
            (
                contract.real_source_construction_budget,
                contract.real_source_open_budget,
                contract.oauth_budget,
                contract.network_budget,
            ),
            (0, 0, 0, 0),
        )
        self.assertFalse(contract.cli_available)
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_dormant_real_dotenv_owner_factory.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "argparse",
            "input(",
            "subprocess",
            "execution_enabled=true",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
