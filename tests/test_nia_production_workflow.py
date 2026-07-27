import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "main_nia-v365-next-api.yml"


class NiaProductionWorkflowTests(unittest.TestCase):
    def test_full_local_regression_precedes_packaging_and_deployment(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        regression = "python -m unittest discover -s tests"

        self.assertIn(regression, source)
        self.assertLess(source.index(regression), source.index("upload-artifact@v4"))
        self.assertLess(source.index(regression), source.index("azure/webapps-deploy@v3"))

    def test_regression_step_does_not_activate_or_configure_connector(self):
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertNotIn("NIA_BITRIX_R0_BRIDGE_ENABLED=true", source)
        self.assertNotIn("NIA_BITRIX_MODULE_ENABLED=true", source)
        self.assertNotIn("az webapp config", source)


if __name__ == "__main__":
    unittest.main()
