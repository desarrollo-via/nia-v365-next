import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "r1_key_vault_linux_provisioning_manifest_v1.md"
EXPECTED_SHA256 = "16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49"


class R1KeyVaultLinuxProvisioningManifestV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = MANIFEST.read_bytes()
        cls.text = cls.raw.decode("utf-8")

    def test_manifest_hash_is_exact(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest().upper(), EXPECTED_SHA256)

    def test_inventory_and_scope_are_exact(self):
        for value in (
            "INVENTORY-V2-EXACT-READY",
            "0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9",
            "nia-v365-next-api_group",
            "nia-v365-next-api",
            "nia-next-r1-kv-260810",
            "nia-next-bitrix-r1-protected-settings-v1",
            "NIA_BITRIX_KEY_VAULT_URL",
            "4633458b-17de-408a-b874-0445c86b69e6",
        ):
            self.assertIn(value, self.text)

    def test_baselines_and_zero_effects_are_visible(self):
        for value in (
            "Identidad system-assigned: ausente",
            "vault y el principal\n  no existen",
            "Escrituras Azure 0",
            "lecturas de App Settings 0",
            "lecturas de secretos 0",
            "reintentos 0",
        ):
            self.assertIn(value, self.text)

    def test_rollback_is_surface_specific(self):
        for value in (
            "NO-GO-BEFORE-WRITE",
            "NO-GO-REMAINDER",
            "assignment ID",
            "soft-delete",
            "`purge` queda prohibido",
        ):
            self.assertIn(value, self.text)

    def test_temporary_writer_is_exact_and_removed(self):
        for value in (
            "Key Vault Secrets Officer",
            "b86a8fe4-44ce-4948-aee5-eccb2c155cd7",
            "5e76b332-d208-4129-9ad2-cc760bb23d1f",
            "retirar una sola vez el assignment temporal escritor",
        ):
            self.assertIn(value, self.text)

    def test_manifest_does_not_authorize_production(self):
        self.assertIn("ATTENTION-REQUIRED-AZURE-AUTHENTICATION", self.text)
        self.assertIn("No autoriza abrir la fuente", self.text)
        self.assertIn("no habilita R1", self.text)
        self.assertIn("no modifica Bitrix", self.text)


if __name__ == "__main__":
    unittest.main()
