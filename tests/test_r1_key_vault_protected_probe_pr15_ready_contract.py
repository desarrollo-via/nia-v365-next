import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "r1_key_vault_protected_probe_pr15_ready_contract.md"


class R1KeyVaultProtectedProbePr15ReadyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CONTRACT.read_text(encoding="utf-8")

    def test_state_is_local_and_not_authorized(self):
        self.assertIn(
            "Estado: `PR15-READY-VERIFIED-MERGE-COMPLETED`",
            self.text,
        )
        self.assertIn("No autoriza ready por sí mismo", self.text)

    def test_identity_is_exact(self):
        for value in (
            "PR: `#15`",
            "d5b2325a7025fb00b9d5dde0f20e45ab8217f43b",
            "codex/r1-keyvault-protected-probe-v0580",
            "d037031bba10d5dc21f81c5f7ec9aa647c07884e",
            "765126e381380e2a5525669a6cafb93391eaf957",
        ):
            self.assertIn(value, self.text)

    def test_title_and_body_are_fixed(self):
        self.assertIn("Add protected R1 host probe", self.text)
        self.assertIn("1638 bytes", self.text)
        self.assertIn(
            "2C3DB574268C45F41BF7C51D63244CACBB7625A7F67960868DCC5941EFBCAABB",
            self.text,
        )

    def test_preflight_has_nine_barriers(self):
        for number in range(1, 10):
            self.assertIn(f"{number}.", self.text)
        self.assertIn("31449006990 completed/success", self.text)

    def test_ready_command_is_single_and_exact(self):
        self.assertIn("gh pr ready 15 --repo desarrollo-via/nia-v365-next", self.text)
        self.assertIn("una sola tentativa", self.text)

    def test_postread_is_bounded(self):
        self.assertIn("0, 2, 5, 10, 20, 30", self.text)
        self.assertIn("draft=false", self.text)
        self.assertIn("PR15-READY-VERIFIED-MERGE-NOT-AUTHORIZED", self.text)

    def test_rollback_is_exact(self):
        self.assertIn("gh pr ready 15 --undo", self.text)
        self.assertIn("OPEN/DRAFT", self.text)
        self.assertIn("NO-GO-REMAINDER", self.text)

    def test_ref_is_never_moved(self):
        self.assertIn("Nunca se mueve o elimina la ref", self.text)

    def test_merge_and_external_effects_are_forbidden(self):
        for value in ("merge", "Actions manuales", "despliegue", "Bitrix"):
            self.assertIn(value, self.text)


if __name__ == "__main__":
    unittest.main()
