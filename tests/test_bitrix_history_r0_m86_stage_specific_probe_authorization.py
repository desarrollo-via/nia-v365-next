import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AU_AUTHORIZATION_LITERAL,
    M86AU_PUBLIC_CATEGORIES,
    M86AUAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


class M86AUStageSpecificProbeAuthorizationTests(unittest.TestCase):
    def test_literal_is_prepared_but_not_shown_received_or_linked(self):
        contract = M86AUAuthorizationContract()
        self.assertEqual(contract.state, "PREPARED-NOT-SHOWN")
        self.assertFalse(contract.shown_to_person)
        self.assertFalse(contract.authorization_received)
        self.assertFalse(contract.linked_to_execution)
        self.assertEqual(contract.current_real_read_budget, 0)

    def test_literal_names_exact_keys_and_categories_once(self):
        for name in PROTECTED_SETTING_NAMES:
            self.assertEqual(M86AU_AUTHORIZATION_LITERAL.count(name), 1)
        for category in M86AU_PUBLIC_CATEGORIES:
            self.assertEqual(M86AU_AUTHORIZATION_LITERAL.count(category), 1)
        self.assertNotIn("source_aggregate_unavailable", M86AU_AUTHORIZATION_LITERAL)

    def test_only_exact_literal_is_accepted(self):
        contract = M86AUAuthorizationContract()
        self.assertTrue(contract.accepts(M86AU_AUTHORIZATION_LITERAL))
        self.assertFalse(contract.accepts(M86AU_AUTHORIZATION_LITERAL + " "))
        self.assertFalse(contract.accepts("sp"))

    def test_denials_remain_frozen(self):
        for fragment in (
            "sin enumerar el entorno",
            "No autorizo fallback",
            "claves individuales, progreso o número de lecturas",
            "OAuth, Mongo, red, Bitrix, NIA, historial, mensajes, reintentos",
        ):
            self.assertIn(fragment, M86AU_AUTHORIZATION_LITERAL)


if __name__ == "__main__":
    unittest.main()
