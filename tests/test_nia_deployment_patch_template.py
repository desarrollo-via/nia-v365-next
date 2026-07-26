import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = (
    ROOT
    / "deploy"
    / "templates"
    / "main_nia-v365-next-api.supervisor.patch.example"
)


class NiaDeploymentPatchTemplateTests(unittest.TestCase):
    def test_template_is_inert_and_targets_only_the_real_remote_workflow(self) -> None:
        text = PATCH.read_text(encoding="utf-8")
        self.assertNotEqual(PATCH.parent, ROOT / ".github" / "workflows")
        self.assertIn(
            "a/.github/workflows/main_nia-v365-next-api.yml",
            text,
        )
        self.assertNotIn("desarrollo_nia-v365.yml", text)

    def test_patch_adds_only_isolated_validation(self) -> None:
        text = PATCH.read_text(encoding="utf-8")
        self.assertIn("tests.test_nia_process_launcher", text)
        self.assertIn("tests.test_nia_process_supervisor", text)
        self.assertIn("tests.test_optional_bitrix_connector", text)
        self.assertNotIn("az webapp config set", text)
        self.assertNotIn("NIA_BITRIX_MODULE_ENABLED=true", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("azure/webapps-deploy", text)


if __name__ == "__main__":
    unittest.main()
