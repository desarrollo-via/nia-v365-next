import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m86_dotenv_preflight_authorization_gate import (
    M86BK_AUTHORIZATION_LITERAL,
    M86BKAuthorizationContract,
    M86BKAuthorizationGate,
)
from bitrix_connector.bitrix_history_r0_m86_executable_real_preflight_factory import (
    M86BNGatePermittedExecutableOwnerFactory,
    audit_m86bn_readiness,
    build_m86bn_real_authorization_gate,
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


class M86BNExecutableRealPreflightFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_literal_constructs_nothing_in_real_profile(self):
        calls = []
        factory = M86BNGatePermittedExecutableOwnerFactory(
            source_builder=lambda: calls.append("source"),
            oauth_builder=lambda: calls.append("oauth"),
            http_client_factory=lambda *_args: calls.append("http"),
        )
        result = await M86BKAuthorizationGate(
            owner_factory=factory,
            execution_profile="real",
        ).run_once(confirm_code="sp")
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertFalse(result.fixture_execution)
        self.assertTrue(result.real_path_bound)
        self.assertFalse(result.real_path_opened)
        self.assertTrue(result.linked_to_real_execution)
        self.assertEqual(calls, [])

    async def test_exact_literal_executes_full_topology_only_with_doubles(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bn-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            http_factory = HermeticPreflightHttpFactory()
            factory = M86BNGatePermittedExecutableOwnerFactory(
                source_builder=lambda: AllowlistedDotenvSource(path),
                oauth_builder=lambda: M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=http_factory,
            )
            result = await M86BKAuthorizationGate(
                owner_factory=factory,
                execution_profile="real",
            ).run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("VERIFIED", "none"))
        self.assertFalse(result.fixture_execution)
        self.assertTrue(result.real_path_bound)
        self.assertTrue(result.real_path_opened)
        self.assertTrue(result.linked_to_real_execution)
        self.assertTrue(result.combined_preflight_verified)
        self.assertTrue(result.private_resources_closed)
        self.assertEqual(len(http_factory.requests), 4)
        preview = factory.preview()
        self.assertTrue(preview.permit_consumed)
        self.assertEqual(
            (
                preview.factory_calls,
                preview.source_constructions,
                preview.oauth_constructions,
                preview.owner_constructions,
            ),
            (1, 1, 1, 1),
        )

    def test_direct_call_is_blocked(self):
        calls = []
        factory = M86BNGatePermittedExecutableOwnerFactory(
            source_builder=lambda: calls.append("source"),
            oauth_builder=lambda: calls.append("oauth"),
            http_client_factory=lambda *_args: calls.append("http"),
        )
        with self.assertRaisesRegex(RuntimeError, "gate_permit_required"):
            factory()
        self.assertEqual(calls, [])

    def test_readiness_is_ready_to_show_without_invoking_real_factory(self):
        target = (
            "bitrix_connector.bitrix_history_r0_m86_executable_real_preflight_factory."
            "AllowlistedDotenvSource"
        )
        with patch(target, side_effect=AssertionError("must-not-construct")) as source:
            factory = M86BNGatePermittedExecutableOwnerFactory(
                source_builder=lambda: AllowlistedDotenvSource(Path("forbidden")),
                oauth_builder=lambda: M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=HermeticPreflightHttpFactory(),
            )
            result = audit_m86bn_readiness(
                factory=factory,
                authorization=M86BKAuthorizationContract(),
            )
        source.assert_not_called()
        self.assertEqual(result.state, "READY-TO-SHOW-PREFLIGHT-AUTHORIZATION")
        self.assertTrue(result.exact_gate_bound)
        self.assertTrue(result.executable_factory_dormant)
        self.assertTrue(result.literal_prepared)
        self.assertFalse(result.literal_shown)
        self.assertFalse(result.authorization_received)
        self.assertEqual(
            (
                result.real_source_open_calls,
                result.real_oauth_load_calls,
                result.real_http_calls,
                result.external_calls,
            ),
            (0, 0, 0, 0),
        )

    def test_default_real_gate_build_is_inert_until_run(self):
        target = (
            "bitrix_connector.bitrix_history_r0_m86_executable_real_preflight_factory."
            "AllowlistedDotenvSource"
        )
        with patch(target, side_effect=AssertionError("must-not-construct")) as source:
            gate = build_m86bn_real_authorization_gate()
        source.assert_not_called()
        self.assertIsInstance(gate, M86BKAuthorizationGate)

    def test_module_has_no_cli_or_implicit_execution(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_executable_real_preflight_factory.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "argparse",
            "input(",
            "subprocess",
            "asyncio.run",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
