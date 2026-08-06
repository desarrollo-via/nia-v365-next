import unittest

from bitrix_connector.bitrix_history_r0_m86_environment_probe_authorization import (
    M86AF_AUTHORIZATION_LITERAL,
    M86AFAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


class M86AFAuthorizationContractTests(unittest.TestCase):
    def test_literal_names_all_exact_keys_and_is_not_executable(self):
        contract = M86AFAuthorizationContract()
        self.assertEqual((contract.phase, contract.state), ("M86-AF", "PREPARED-NOT-EXECUTABLE"))
        self.assertFalse(contract.execution_surface_present)
        self.assertFalse(contract.authorization_received)
        for name in PROTECTED_SETTING_NAMES:
            self.assertEqual(M86AF_AUTHORIZATION_LITERAL.count(name), 1)

    def test_only_exact_literal_is_accepted_as_text(self):
        contract = M86AFAuthorizationContract()
        self.assertTrue(contract.accepts(M86AF_AUTHORIZATION_LITERAL))
        self.assertFalse(contract.accepts(M86AF_AUTHORIZATION_LITERAL + " "))
        self.assertFalse(contract.accepts("sp"))

    def test_literal_freezes_all_denials(self):
        for fragment in (
            "una única tentativa agregada",
            "sin enumerar el entorno",
            "FIT o NO-GO",
            "No autorizo fallback",
            "Credential Manager",
            "OAuth, Mongo, red, Bitrix, NIA, historial, mensajes, reintentos",
        ):
            self.assertIn(fragment, M86AF_AUTHORIZATION_LITERAL)


if __name__ == "__main__":
    unittest.main()
