import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m86_combined_preflight_owner import (
    M86CombinedPreflightOwner,
)
from bitrix_connector.bitrix_history_r0_m86_dotenv_preflight_authorization_gate import (
    M86BK_AUTHORIZATION_LITERAL,
    M86BKFixtureAuthorizationGate,
)
from bitrix_connector.bitrix_history_r0_m86_gate_permitted_real_owner_factory import (
    M86BMFactoryContract,
    M86BMGatePermittedRealOwnerFactory,
    build_m86bm_gate_permitted_real_owner_factory,
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


class M86BMGatePermittedRealOwnerFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_literal_constructs_nothing(self):
        calls = []
        factory = M86BMGatePermittedRealOwnerFactory(
            source_builder=lambda: calls.append("source"),
            oauth_builder=lambda: calls.append("oauth"),
            http_client_factory=lambda *_args: calls.append("http"),
        )
        result = await M86BKFixtureAuthorizationGate(
            owner_factory=factory
        ).run_once(confirm_code="sp")
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertEqual(calls, [])
        self.assertEqual(factory.preview().factory_calls, 0)

    async def test_exact_gate_composes_disabled_owner_once_with_substitutes(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bm-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            calls = []

            def owner_builder(**kwargs):
                calls.append(kwargs["hermetic_execution"])
                return M86CombinedPreflightOwner(**kwargs)

            factory = M86BMGatePermittedRealOwnerFactory(
                source_builder=lambda: AllowlistedDotenvSource(path),
                oauth_builder=lambda: M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=HermeticPreflightHttpFactory(),
                owner_builder=owner_builder,
            )
            with patch.object(
                AllowlistedDotenvSource,
                "open",
                new=AsyncMock(side_effect=AssertionError("must-not-open")),
            ) as open_mock:
                result = await M86BKFixtureAuthorizationGate(
                    owner_factory=factory
                ).run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
            open_mock.assert_not_awaited()
        self.assertEqual(result.failure_category, "preflight_no_go")
        self.assertTrue(result.authorization_consumed)
        self.assertEqual(calls, [False])
        preview = factory.preview()
        self.assertTrue(preview.permit_consumed)
        self.assertEqual(
            (
                preview.factory_calls,
                preview.source_constructions,
                preview.oauth_constructions,
                preview.owner_constructions,
                preview.source_open_calls,
                preview.oauth_load_calls,
                preview.http_calls,
            ),
            (1, 1, 1, 1, 0, 0, 0),
        )

    def test_direct_call_is_blocked_without_construction(self):
        calls = []
        factory = M86BMGatePermittedRealOwnerFactory(
            source_builder=lambda: calls.append("source"),
            oauth_builder=lambda: calls.append("oauth"),
            http_client_factory=lambda *_args: calls.append("http"),
        )
        with self.assertRaisesRegex(RuntimeError, "gate_permit_required"):
            factory()
        self.assertEqual(calls, [])
        self.assertEqual(factory.preview().factory_calls, 0)

    async def test_factory_is_one_shot_after_gate(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bm-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            factory = M86BMGatePermittedRealOwnerFactory(
                source_builder=lambda: AllowlistedDotenvSource(path),
                oauth_builder=lambda: M86StoredOAuthBackend(
                    resources_factory=OAuthFactoryFixture()
                ),
                http_client_factory=HermeticPreflightHttpFactory(),
            )
            gate = M86BKFixtureAuthorizationGate(owner_factory=factory)
            await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
            second = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual(second.failure_category, "gate_reused")
        self.assertEqual(factory.preview().factory_calls, 1)

    async def test_default_real_factory_preview_does_not_construct(self):
        target = (
            "bitrix_connector.bitrix_history_r0_m86_gate_permitted_real_owner_factory."
            "AllowlistedDotenvSource"
        )
        with patch(target, side_effect=AssertionError("must-not-construct")) as source:
            factory = build_m86bm_gate_permitted_real_owner_factory()
            preview = factory.preview()
        source.assert_not_called()
        self.assertFalse(preview.permit_consumed)
        self.assertEqual((preview.factory_calls, preview.source_constructions), (0, 0))
        self.assertFalse(preview.owner_hermetic_execution)
        self.assertFalse(preview.real_execution_authorized)

    def test_contract_and_module_have_no_cli_or_enabled_owner(self):
        contract = M86BMFactoryContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BM", "GATE-PERMITTED-NOT-EXECUTABLE"))
        self.assertTrue(contract.exact_gate_permit_required)
        self.assertFalse(contract.direct_call_allowed)
        self.assertTrue(contract.one_shot)
        self.assertFalse(contract.owner_hermetic_execution)
        self.assertEqual(
            (
                contract.real_source_open_budget,
                contract.real_oauth_load_budget,
                contract.real_http_budget,
            ),
            (0, 0, 0),
        )
        self.assertFalse(contract.cli_available)
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_gate_permitted_real_owner_factory.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "argparse",
            "input(",
            "subprocess",
            "hermetic_execution=true",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
