import unittest

from bitrix_connector.bitrix_history_r0_m86_categorical_probe_authorization import (
    M86AO_AUTHORIZATION_LITERAL,
    M86AOAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_m86_public_aggregate_diagnostic import (
    PUBLIC_FAILURE_CATEGORIES,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


class M86AOAuthorizationTests(unittest.TestCase):
    def test_literal_is_prepared_but_not_shown_or_received(self):
        contract = M86AOAuthorizationContract()
        self.assertEqual(contract.state, "PREPARED-NOT-SHOWN")
        self.assertFalse(contract.shown_to_person)
        self.assertFalse(contract.authorization_received)
        self.assertEqual(contract.current_real_read_budget, 0)

    def test_literal_names_exact_keys_once(self):
        for name in PROTECTED_SETTING_NAMES:
            self.assertEqual(M86AO_AUTHORIZATION_LITERAL.count(name), 1)

    def test_literal_names_only_allowlisted_categories(self):
        for category in PUBLIC_FAILURE_CATEGORIES:
            self.assertEqual(M86AO_AUTHORIZATION_LITERAL.count(category), 1)

    def test_only_exact_literal_is_accepted_as_text(self):
        contract = M86AOAuthorizationContract()
        self.assertTrue(contract.accepts(M86AO_AUTHORIZATION_LITERAL))
        self.assertFalse(contract.accepts(M86AO_AUTHORIZATION_LITERAL + " "))
        self.assertFalse(contract.accepts("sp"))

    def test_denials_are_frozen(self):
        for fragment in (
            "sin enumerar el entorno",
            "No autorizo fallback",
            "claves individuales, progreso o número de lecturas",
            "OAuth, Mongo, red, Bitrix, NIA, historial, mensajes, reintentos",
        ):
            self.assertIn(fragment, M86AO_AUTHORIZATION_LITERAL)


if __name__ == "__main__":
    unittest.main()
