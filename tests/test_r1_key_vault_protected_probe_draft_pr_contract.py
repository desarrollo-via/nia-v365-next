import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "r1_key_vault_protected_probe_draft_pr_contract.md"
BODY = ROOT / "docs" / "r1_key_vault_protected_probe_draft_pr_body.md"


class R1KeyVaultProtectedProbeDraftPrContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.body_bytes = BODY.read_bytes()
        cls.body = cls.body_bytes.decode("utf-8")

    def test_contract_is_prepared_but_not_authorized(self):
        self.assertIn("Estado: `DRAFT-PR-CREATED-VERIFIED-READY-NOT-AUTHORIZED`", self.contract)
        self.assertIn("no autoriza red ni crear el PR", self.contract)

    def test_identity_is_exact(self):
        for value in (
            "desarrollo-via/nia-v365-next",
            "d5b2325a7025fb00b9d5dde0f20e45ab8217f43b",
            "codex/r1-keyvault-protected-probe-v0580",
            "d037031bba10d5dc21f81c5f7ec9aa647c07884e",
            "765126e381380e2a5525669a6cafb93391eaf957",
        ):
            self.assertIn(value, self.contract)

    def test_body_size_and_hash_are_fixed(self):
        self.assertEqual(len(self.body_bytes), 1638)
        self.assertEqual(
            hashlib.sha256(self.body_bytes).hexdigest().upper(),
            "2C3DB574268C45F41BF7C51D63244CACBB7625A7F67960868DCC5941EFBCAABB",
        )

    def test_creation_is_single_draft_attempt(self):
        self.assertIn("gh pr create --repo desarrollo-via/nia-v365-next", self.contract)
        self.assertIn("--head codex/r1-keyvault-protected-probe-v0580", self.contract)
        self.assertIn("--draft --title \"Add protected R1 host probe\"", self.contract)
        self.assertIn("una sola tentativa", self.contract)

    def test_preflight_requires_effect_absence_and_stability(self):
        for value in (
            "cero PR abiertos o históricos",
            "cero Actions, checks",
            "31449006990 completed/success",
            "31/31",
            "1781/1781",
            "tc 9/9",
        ):
            self.assertIn(value, self.contract)

    def test_postread_is_bounded_and_exact(self):
        self.assertIn("0, 2, 5, 10, 20,", self.contract)
        self.assertIn("OPEN/DRAFT", self.contract)
        self.assertIn("DRAFT-PR-CREATED-VERIFIED", self.contract)

    def test_rollback_never_moves_the_ref(self):
        self.assertIn("gh pr close <PR_NUEVO>", self.contract)
        self.assertIn("La ref no se mueve ni elimina", self.contract)
        self.assertIn("NO-GO-REMAINDER", self.contract)

    def test_forbidden_external_effects_remain_explicit(self):
        for value in ("merge", "Actions manuales", "despliegue", "Bitrix"):
            self.assertIn(value, self.contract)

    def test_body_states_scope_and_limits(self):
        self.assertIn("seis rutas", self.body)
        self.assertIn("cero cambios bajo `.github/workflows/`", self.body)
        self.assertIn("NIA_BITRIX_KEY_VAULT_URL", self.body)
        self.assertIn("El PR debe permanecer borrador", self.body)


if __name__ == "__main__":
    unittest.main()
