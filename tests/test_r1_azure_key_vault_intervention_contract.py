import unittest
from pathlib import Path

from bitrix_connector.r1_key_vault_linux_provisioning_owner import (
    SECOND_CONFIRMATION_TEXT,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "r1_azure_key_vault_intervention_contract.md"


class R1AzureKeyVaultInterventionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CONTRACT.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()

    def test_contract_is_inventory_ready_but_provisioning_blocked(self):
        self.assertIn("ARTIFACT-VERIFIED-RUNTIME-SETTING-EXTERNAL-BLOCKED", self.text)
        self.assertIn("R1-KV-2026-08-10-V1", self.text)
        self.assertIn(
            "EXPIRED-AWAITING-AZURE-AUTHENTICATION-AND-LISTO",
            self.text,
        )
        self.assertIn("respuesta exacta `listo`", self.text)

    def test_fixed_resource_identity_is_present(self):
        for value in ("nia-v365-next-api", "Production", "viaindustrial-core"):
            self.assertIn(value, self.text)

    def test_inventory_baselines_are_explicit(self):
        for value in (
            "App Setting no secreta exacta",
            "identidad administrada ausente",
            "resource IDs exactos",
        ):
            self.assertIn(value, self.text)

    def test_inventory_authorization_is_exact_and_one_shot(self):
        literal = "AUTORIZO INVENTARIO AZURE R1 SOLO LECTURA R1-KV-2026-08-10-V1"
        self.assertEqual(self.text.count(literal), 1)
        self.assertIn("cero reintentos", self.text)

    def test_preflight_sp_and_productive_confirmation_are_separate(self):
        self.assertIn("Respuesta ligada: sp", self.text)
        self.assertEqual(self.text.count(SECOND_CONFIRMATION_TEXT), 1)
        self.assertNotIn(
            "\nCONFIRMACION R1 KEYVAULT LINUX",
            self.text,
        )
        manifest_hash = "16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49"
        self.assertEqual(self.text.count(manifest_hash), 2)
        self.assertNotIn("<HUELLA-MANIFIESTO>", self.text)

    def test_exact_secret_and_nonsecret_setting_are_fixed(self):
        self.assertIn("nia-next-bitrix-r1-protected-settings-v1", self.text)
        self.assertIn("NIA_BITRIX_KEY_VAULT_URL", self.text)

    def test_document_does_not_authorize_current_external_action(self):
        self.assertIn("Este documento no autoriza", self.text)
        self.assertIn("Credential Manager", self.text)
        self.assertIn("escritura continúan bloqueados", self.text)

    def test_rollback_preserves_preexisting_identity_and_uses_exact_ids(self):
        self.assertIn("si era previa se preserva", self.text)
        self.assertIn("assignment ID", self.text)
        self.assertIn("NO-GO-REMAINDER", self.text)

    def test_destructive_or_broad_surfaces_are_prohibited(self):
        self.assertIn("purge` está prohibido", self.text)
        self.assertIn("enumeración del diccionario de App Settings", self.text)
        self.assertIn("nunca hard reset, force push", self.text)


if __name__ == "__main__":
    unittest.main()
