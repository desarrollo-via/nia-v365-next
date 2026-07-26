import unittest
from pathlib import Path


class OAuthInstallationLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "lanzar_bitrix_oauth_installation.ps1"
        ).read_text(encoding="utf-8")

    def test_uses_isolated_entrypoint_and_never_main(self):
        self.assertIn(
            "bitrix_connector.installation_entrypoint:app",
            self.script,
        )
        self.assertNotIn("main:app", self.script)

    def test_forces_safe_child_state(self):
        for expected in (
            'NIA_BITRIX_MODE = "off"',
            'NIA_BITRIX_INSTALLATION_ENABLED = "true"',
            'NIA_BITRIX_PILOT_ENABLED = "false"',
            'NIA_BITRIX_PILOT_EMERGENCY_STOP = "true"',
        ):
            self.assertIn(expected, self.script)
        self.assertIn("oauth_install_local_safety_state_invalid", self.script)
        self.assertIn("oauth_install_public_safety_state_invalid", self.script)

    def test_tunnel_is_temporary_and_cleanup_targets_owned_processes(self):
        self.assertIn("trycloudflare", self.script)
        self.assertIn("Stop-OwnedProcess -Process $tunnelProcess", self.script)
        self.assertIn("Stop-OwnedProcess -Process $serverProcess", self.script)
        self.assertNotIn("Get-Process -Name cloudflared", self.script)

    def test_does_not_embed_or_print_environment_secrets(self):
        self.assertNotIn("NIA_BITRIX_MONGO_URI=", self.script)
        self.assertNotIn("NIA_BITRIX_CLIENT_SECRET=", self.script)
        self.assertNotIn("Get-Content -LiteralPath $envPath", self.script)


if __name__ == "__main__":
    unittest.main()
