import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m86_fixture_dotenv_bridge import (
    M86BCFixtureDotenvBridgeContract,
    M86BCFixtureDotenvBridgeOwner,
)
from bitrix_connector.bitrix_history_r0_m86_dotenv_probe_authorization import (
    M86BD_AUTHORIZATION_LITERAL,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AU_AUTHORIZATION_LITERAL,
)
from bitrix_connector.bitrix_history_r0_protected_dotenv_source import (
    AllowlistedDotenvSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


ROOT = Path(__file__).resolve().parents[1]


def fixture_payload(*, omit=None):
    return b"\n".join(
        f"{name}=fixture-m86-bc-{index}".encode("ascii")
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
        if name != omit
    ) + b"\n"


class M86BCFixtureDotenvBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def _run_payload(self, payload, confirm_code=M86BD_AUTHORIZATION_LITERAL):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bc-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(payload)
            result = await M86BCFixtureDotenvBridgeOwner().run_once(
                source=AllowlistedDotenvSource(path),
                confirm_code=confirm_code,
            )
            return result

    async def test_fixture_dotenv_reaches_categorical_fit(self):
        result = await self._run_payload(fixture_payload())
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))
        self.assertTrue(result.aggregate_transferred)
        self.assertTrue(result.source_closed)
        self.assertFalse(result.values_exposed)
        self.assertFalse(result.immutable_text_created)

    async def test_missing_fixture_value_fails_before_owner(self):
        result = await self._run_payload(
            fixture_payload(omit=PROTECTED_SETTING_NAMES[-1])
        )
        self.assertEqual(
            (result.state, result.failure_category),
            ("NO-GO", "source_transfer_unavailable"),
        )
        self.assertFalse(result.aggregate_transferred)
        self.assertTrue(result.source_closed)

    async def test_wrong_literal_does_not_open_fixture(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bc-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            source = AllowlistedDotenvSource(path)
            open_mock = AsyncMock()
            with patch.object(AllowlistedDotenvSource, "open", new=open_mock):
                result = await M86BCFixtureDotenvBridgeOwner().run_once(
                    source=source,
                    confirm_code="sp",
                )
            open_mock.assert_not_awaited()
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertTrue(result.source_closed)

    async def test_source_cleanup_failure_is_terminal(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bc-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            source = AllowlistedDotenvSource(path)
            with patch.object(
                AllowlistedDotenvSource,
                "close",
                new=AsyncMock(side_effect=RuntimeError),
            ):
                result = await M86BCFixtureDotenvBridgeOwner().run_once(
                    source=source,
                    confirm_code=M86BD_AUTHORIZATION_LITERAL,
                )
        self.assertEqual(result.failure_category, "cleanup_ambiguous")
        self.assertTrue(result.aggregate_transferred)
        self.assertFalse(result.source_closed)

    async def test_owner_is_one_shot(self):
        owner = M86BCFixtureDotenvBridgeOwner()
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bc-") as directory:
            first_path = Path(directory) / "protected-fixture.env"
            first_path.write_bytes(fixture_payload())
            await owner.run_once(
                source=AllowlistedDotenvSource(first_path),
                confirm_code=M86BD_AUTHORIZATION_LITERAL,
            )
            with self.assertRaisesRegex(RuntimeError, "reuse_or_source_invalid"):
                await owner.run_once(
                    source=AllowlistedDotenvSource(first_path),
                    confirm_code=M86BD_AUTHORIZATION_LITERAL,
                )

    async def test_legacy_m86au_literal_does_not_open_fixture(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-m86-bc-") as directory:
            path = Path(directory) / "protected-fixture.env"
            path.write_bytes(fixture_payload())
            source = AllowlistedDotenvSource(path)
            open_mock = AsyncMock()
            with patch.object(AllowlistedDotenvSource, "open", new=open_mock):
                result = await M86BCFixtureDotenvBridgeOwner().run_once(
                    source=source,
                    confirm_code=M86AU_AUTHORIZATION_LITERAL,
                )
            open_mock.assert_not_awaited()
        self.assertEqual(result.failure_category, "authorization_invalid")

    def test_contract_and_source_have_no_real_route(self):
        contract = M86BCFixtureDotenvBridgeContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BC", "FIXTURE-ONLY-INERT"))
        self.assertTrue(contract.source_must_be_injected)
        self.assertFalse(contract.real_path_factory_present)
        self.assertTrue(contract.direct_bytearray_transfer)
        self.assertEqual(contract.exact_authorization_phase, "M86-BD")
        self.assertFalse(contract.legacy_authorization_accepted)
        self.assertFalse(contract.immutable_text_handoff_allowed)
        self.assertEqual((contract.exact_name_budget, contract.enumeration_budget), (7, 0))
        self.assertEqual(contract.fallback_budget, 0)
        self.assertFalse(contract.cli_available)
        self.assertFalse(contract.real_execution_authorized)
        self.assertEqual(contract.external_calls, 0)

        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_fixture_dotenv_bridge.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            'path(".env")',
            "path('.env')",
            "os.environ",
            "getenv",
            "ctypes",
            "credread",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
