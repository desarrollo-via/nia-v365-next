import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (ROOT / "docs" / "r1_key_vault_provisioning_probe_cut_inventory.md").read_text(encoding="utf-8")
CONTRACT = (ROOT / "docs" / "r1_key_vault_provisioning_probe_publication_contract.md").read_text(encoding="utf-8")
BODY = (ROOT / "docs" / "r1_key_vault_provisioning_probe_draft_pr_body.md").read_text(encoding="utf-8")


class R1KeyVaultProvisioningProbePublicationContractTests(unittest.TestCase):
    def test_identity_is_exact_across_documents(self):
        for value in (
            "1b4c2be1ce68e889a19dd9c92c91a51c857ab0c4",
            "2631f8483ca5e565b4ca53874e32f4d6035c09f8",
            "9e743a9bdde1ac5c1bb8786000c50e94ff9ac597",
        ):
            self.assertIn(value, INVENTORY)
            self.assertIn(value, CONTRACT)
            self.assertIn(value, BODY)

    def test_scope_is_three_routes_and_zero_workflows(self):
        self.assertIn("Rutas: 3; workflows: 0", INVENTORY)
        self.assertIn("tres rutas", CONTRACT)
        self.assertIn("cero workflows", CONTRACT)
        self.assertIn("1702/1702", INVENTORY)

    def test_remote_effects_are_closed_and_protected_effects_remain_outside(self):
        self.assertIn("MERGED-DEPLOYED-STABLE", CONTRACT)
        self.assertIn("31518711951", CONTRACT)
        self.assertIn("cero Actions manuales", CONTRACT)
        self.assertIn("No se invocó la sonda", CONTRACT)

    def test_rollback_is_normal_and_exact(self):
        for value in (
            "cerrar sólo el PR",
            "eliminar sólo la rama exacta",
            "revert normal",
            "fast-forward normal",
            "nunca reset o\n  force-push",
            "NO-GO-REMAINDER",
        ):
            self.assertIn(value, CONTRACT)

    def test_envelope_stops_before_protected_or_productive_surfaces(self):
        for value in (
            "invocar la nueva sonda",
            "Credential Manager",
            "autenticar Azure",
            "activar R1",
            "consultar Bitrix",
            "enviar mensajes",
        ):
            self.assertIn(value, CONTRACT)


if __name__ == "__main__":
    unittest.main()
