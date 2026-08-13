import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "r1_key_vault_protected_probe_pr15_merge_contract.md"


class R1KeyVaultProtectedProbePr15MergeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CONTRACT.read_text(encoding="utf-8")

    def test_state_waits_for_ready(self):
        self.assertIn("Estado: `MERGED-DEPLOYED-STABLE`", self.text)

    def test_identity_is_exact(self):
        for value in (
            "d5b2325a7025fb00b9d5dde0f20e45ab8217f43b",
            "d037031bba10d5dc21f81c5f7ec9aa647c07884e",
            "765126e381380e2a5525669a6cafb93391eaf957",
            "7214bbb08ded045d59b6eb7ea0710b6fc68c18f8",
        ):
            self.assertIn(value, self.text)

    def test_scope_and_workflow_are_fixed(self):
        self.assertIn("seis rutas", self.text)
        self.assertIn("cero workflows", self.text)
        self.assertIn("8861d91a27250cfef93d606bfd8a4414a5fb024c", self.text)

    def test_preflight_has_eight_barriers(self):
        for number in range(1, 9):
            self.assertIn(f"{number}.", self.text)

    def test_merge_command_is_exact(self):
        self.assertIn("gh pr merge 15 --repo desarrollo-via/nia-v365-next", self.text)
        self.assertIn("--merge --match-head-commit d037031b", self.text)

    def test_unsafe_merge_options_are_forbidden(self):
        for value in ("`--admin`", "`--auto`", "`--delete-branch`"):
            self.assertIn(value, self.text)

    def test_automatic_workflow_is_bounded(self):
        self.assertIn("máximo 120 segundos", self.text)
        self.assertIn("cada 10 segundos hasta 15 minutos", self.text)
        self.assertIn("completed/success", self.text)

    def test_health_and_external_limits_are_explicit(self):
        self.assertIn("dos lecturas de salud separadas por 10 segundos", self.text)
        for value in ("Azure", "Bitrix", "secretos"):
            self.assertIn(value, self.text)

    def test_rollback_is_normal_and_never_forces(self):
        self.assertIn("revert normal", self.text)
        self.assertIn("fast-forward normal", self.text)
        self.assertIn("sin reset, force-push", self.text)
        self.assertIn("NO-GO-REMAINDER", self.text)


if __name__ == "__main__":
    unittest.main()
