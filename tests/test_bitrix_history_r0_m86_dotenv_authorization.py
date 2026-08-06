import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_dotenv_authorization_readiness import (
    audit_m86bd_readiness,
)
from bitrix_connector.bitrix_history_r0_m86_dotenv_probe_authorization import (
    M86BD_AUTHORIZATION_LITERAL,
    M86BD_PUBLIC_CATEGORIES,
    M86BDAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_m86_fixture_dotenv_bridge import (
    M86BCFixtureDotenvBridgeContract,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


class M86BDDotenvAuthorizationTests(unittest.TestCase):
    def test_contract_is_prepared_but_unshown_unreceived_and_unlinked(self):
        contract = M86BDAuthorizationContract()
        self.assertEqual((contract.phase, contract.state), ("M86-BD", "PREPARED-NOT-SHOWN"))
        self.assertFalse(contract.shown_to_person)
        self.assertFalse(contract.authorization_received)
        self.assertFalse(contract.linked_to_execution)
        self.assertEqual((contract.single_open_budget, contract.current_real_read_budget), (0, 0))

    def test_exact_match_only_and_generic_sp_is_rejected(self):
        contract = M86BDAuthorizationContract()
        self.assertTrue(contract.accepts(M86BD_AUTHORIZATION_LITERAL))
        self.assertFalse(contract.accepts("sp"))
        self.assertFalse(contract.accepts(M86BD_AUTHORIZATION_LITERAL + " "))

    def test_literal_names_each_protected_setting_once(self):
        for name in PROTECTED_SETTING_NAMES:
            self.assertEqual(M86BD_AUTHORIZATION_LITERAL.count(name), 1)

    def test_literal_freezes_single_source_and_prohibitions(self):
        lowered = M86BD_AUTHORIZATION_LITERAL.lower()
        for required in (
            "una única tentativa de apertura",
            "project_root de nia-next",
            "buffers mutables",
            "finally",
            "no autorizo fallback",
            "entorno del proceso",
            "no autorizo mostrar",
            "no-go/cleanup_ambiguous",
        ):
            self.assertIn(required, lowered)
        self.assertEqual(tuple(M86BD_PUBLIC_CATEGORIES)[-1], "cleanup_ambiguous")

    def test_readiness_is_ready_to_show_without_real_budget(self):
        result = audit_m86bd_readiness(
            bridge=M86BCFixtureDotenvBridgeContract(),
            authorization=M86BDAuthorizationContract(),
        )
        self.assertEqual(result.state, "READY-TO-SHOW-DOTENV-AUTHORIZATION")
        self.assertTrue(result.bridge_fixture_only)
        self.assertTrue(result.categories_frozen)
        self.assertTrue(result.literal_prepared)
        self.assertFalse(result.literal_shown)
        self.assertFalse(result.authorization_received)
        self.assertFalse(result.linked_to_execution)
        self.assertFalse(result.real_path_bound)
        self.assertEqual((result.real_open_calls, result.real_read_calls, result.external_calls), (0, 0, 0))

    def test_wrong_contracts_fail_closed(self):
        self.assertEqual(
            audit_m86bd_readiness(
                bridge=object(), authorization=M86BDAuthorizationContract()
            ).state,
            "NO-GO",
        )
        self.assertEqual(
            audit_m86bd_readiness(
                bridge=M86BCFixtureDotenvBridgeContract(), authorization=object()
            ).state,
            "NO-GO",
        )

    def test_readiness_module_has_no_execution_or_source_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_dotenv_authorization_readiness.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "allowlisteddotenvsource",
            "path(",
            ".open(",
            "asyncio",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
            "if __name__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
