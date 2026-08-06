import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m86_dormant_dotenv_preflight_binding import (
    M86BJFixturePreflightOwner,
)
from bitrix_connector.bitrix_history_r0_m86_dotenv_preflight_authorization_gate import (
    M86BK_AUTHORIZATION_LITERAL,
    M86BKAuthorizationContract,
    M86BKFixtureAuthorizationGate,
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
from tests.test_bitrix_history_r0_m86_dormant_dotenv_preflight_binding import (
    fixture_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_gate(path, *, http_factory=None):
    calls = []
    http_factory = http_factory or HermeticPreflightHttpFactory()

    def owner_factory():
        calls.append("owner")
        return M86BJFixturePreflightOwner(
            source=AllowlistedDotenvSource(path),
            oauth_backend=M86StoredOAuthBackend(
                resources_factory=OAuthFactoryFixture()
            ),
            http_client_factory=http_factory,
        )

    return M86BKFixtureAuthorizationGate(owner_factory=owner_factory), calls, http_factory


class M86BKDotenvPreflightAuthorizationGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_literal_does_not_construct_or_open_fixture(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bk-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            gate, calls, _ = fixture_gate(path)
            with patch.object(
                AllowlistedDotenvSource,
                "open",
                new=AsyncMock(side_effect=AssertionError("must-not-open")),
            ) as open_mock:
                result = await gate.run_once(confirm_code="sp")
            open_mock.assert_not_awaited()
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertTrue(result.authorization_consumed)
        self.assertEqual((result.owner_factory_calls, calls), (0, []))

    async def test_exact_literal_runs_fixture_preflight_once(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bk-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            gate, calls, http_factory = fixture_gate(path)
            result = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("VERIFIED", "none"))
        self.assertTrue(result.authorization_exact)
        self.assertTrue(result.authorization_consumed)
        self.assertTrue(result.combined_preflight_verified)
        self.assertTrue(result.private_resources_closed)
        self.assertEqual((result.owner_factory_calls, result.owner_calls), (1, 1))
        self.assertEqual(calls, ["owner"])
        self.assertEqual(len(http_factory.requests), 4)
        self.assertFalse(result.real_path_bound)
        self.assertFalse(result.real_path_opened)
        self.assertFalse(result.linked_to_real_execution)

    async def test_missing_fixture_value_is_terminal_no_go(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bk-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload(omit=PROTECTED_SETTING_NAMES[-1]))
            gate, _, http_factory = fixture_gate(path)
            result = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("NO-GO", "source_stage"))
        self.assertTrue(result.authorization_consumed)
        self.assertEqual(http_factory.requests, [])

    async def test_bot_contract_stage_is_propagated_without_private_detail(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bk-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            gate, _, _ = fixture_gate(
                path,
                http_factory=HermeticPreflightHttpFactory(bot_id=999999),
            )
            result = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual(
            (result.state, result.failure_category),
            ("NO-GO", "bot_contract_stage"),
        )
        self.assertTrue(result.private_resources_closed)

    async def test_gate_reuse_does_not_call_owner_twice(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bk-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            gate, calls, _ = fixture_gate(path)
            await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
            second = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual(second.failure_category, "gate_reused")
        self.assertEqual(calls, ["owner"])

    async def test_cancellation_is_terminal(self):
        class CancelledOwner:
            async def run_once(self):
                raise asyncio.CancelledError()

        gate = M86BKFixtureAuthorizationGate(owner_factory=CancelledOwner)
        result = await gate.run_once(confirm_code=M86BK_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("CANCELLED", "cancelled"))
        self.assertTrue(result.authorization_consumed)

    def test_authorization_is_prepared_unshown_and_not_real_linked(self):
        contract = M86BKAuthorizationContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BK", "PREPARED-NOT-SHOWN"))
        self.assertFalse(contract.shown_to_person)
        self.assertFalse(contract.authorization_received)
        self.assertFalse(contract.linked_to_real_execution)
        self.assertEqual(
            (
                contract.current_real_open_budget,
                contract.current_oauth_budget,
                contract.current_bitrix_read_budget,
                contract.external_calls,
            ),
            (0, 0, 0, 0),
        )
        self.assertTrue(contract.accepts(M86BK_AUTHORIZATION_LITERAL))
        self.assertFalse(contract.accepts("sp"))
        for name in PROTECTED_SETTING_NAMES:
            self.assertEqual(M86BK_AUTHORIZATION_LITERAL.count(name), 1)
        expected_categories = (
            "none",
            "owner_factory_unavailable",
            "preflight_no_go",
            "source_stage",
            "oauth_stage",
            "bot_stage",
            "bot_revision_stage",
            "bot_revision_transport_stage",
            "bot_revision_remote_stage",
            "bot_revision_token_expired_stage",
            "bot_revision_retryable_stage",
            "bot_revision_permanent_stage",
            "bot_revision_contract_stage",
            "bot_list_stage",
            "bot_contract_stage",
            "dialog_stage",
            "contract_stage",
            "cleanup_ambiguous",
            "cancelled",
        )
        category_text = M86BK_AUTHORIZATION_LITERAL.split(
            "failure_category elegida exclusivamente entre ",
            1,
        )[1].split(". Todos los buffers", 1)[0]
        actual_categories = tuple(
            item.strip()
            for item in category_text.replace(" o ", ", ").split(",")
        )
        self.assertEqual(actual_categories, expected_categories)

    def test_module_has_no_real_binding_path_or_command(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_dotenv_preflight_authorization_gate.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "m86bj_dotenv_path",
            "build_dormant_m86bj_binding",
            "allowlisteddotenvsource",
            "argparse",
            "input(",
            "subprocess",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
