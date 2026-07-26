import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy" / "templates" / "g0-azure-webapp.yml.example"
ACTIVE_WORKFLOWS = ROOT / ".github" / "workflows"


class G0WorkflowTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = TEMPLATE.read_text(encoding="utf-8")

    def test_template_is_inert_and_outside_active_workflows(self) -> None:
        self.assertTrue(TEMPLATE.is_file())
        self.assertNotIn(ACTIVE_WORKFLOWS, TEMPLATE.parents)
        self.assertCountEqual(
            [path.name for path in ACTIVE_WORKFLOWS.glob("*.y*ml")],
            ["desarrollo_nia-v365.yml", "main_nia-v365-next-api.yml"],
        )

    def test_only_manual_trigger_is_declared(self) -> None:
        self.assertRegex(self.source, r"(?m)^on:\s*$")
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:\s*$")
        self.assertNotRegex(
            self.source,
            r"(?m)^\s{2}(push|pull_request|schedule|workflow_call):\s*$",
        )

    def test_destination_is_variable_and_nia_v365_is_rejected(self) -> None:
        self.assertIn("vars.NIA_BITRIX_G0_AZURE_WEBAPP_NAME", self.source)
        self.assertIn('"${G0_APP_NAME,,}" == "nia-v365"', self.source)
        self.assertIn("Refusing to deploy G0 to nia-v365.", self.source)
        self.assertNotRegex(self.source, r"(?m)^\s+app-name:\s*['\"]?nia-v365")

    def test_manual_confirmation_and_off_health_are_mandatory(self) -> None:
        self.assertGreaterEqual(self.source.count("DESPLEGAR G0 OFF"), 2)
        self.assertIn("IP-literal G0 origins are forbidden.", self.source)
        self.assertIn("'effective_mode':'off'", self.source)
        self.assertIn("'activation_locked':True", self.source)
        self.assertIn("'external_calls_enabled':False", self.source)
        self.assertIn("'pilot_emergency_stop':True", self.source)

    def test_package_is_minimal_and_contains_no_runtime_secrets(self) -> None:
        self.assertIn("cp -R bitrix_connector g0-package/bitrix_connector", self.source)
        self.assertIn("cp requirements.txt g0-package/requirements.txt", self.source)
        self.assertNotIn("cp main.py", self.source)
        self.assertNotIn("NIA_BITRIX_APPLICATION_TOKEN", self.source)
        self.assertNotIn("/bitrix-connector/webhook", self.source)
        self.assertNotIn("imbot.v2.Bot.register", self.source)
        self.assertNotIn("imbot.v2.Bot.unregister", self.source)


if __name__ == "__main__":
    unittest.main()
