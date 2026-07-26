import unittest

from fastapi.testclient import TestClient

from bitrix_connector.config import load_settings
from bitrix_connector.installation_entrypoint import (
    INSTALLATION_CALLBACK_PATH,
    create_installation_entrypoint,
)


class InstallationEntrypointTests(unittest.TestCase):
    def test_exposes_only_installation_callback_and_safe_health(self):
        settings = load_settings(
            {
                "NIA_BITRIX_MODE": "active",
                "NIA_BITRIX_INSTALLATION_ENABLED": "false",
                "NIA_BITRIX_PILOT_ENABLED": "false",
                "NIA_BITRIX_PILOT_EMERGENCY_STOP": "true",
            }
        )
        app = create_installation_entrypoint(settings_loader=lambda: settings)

        with TestClient(app, base_url="http://localhost") as client:
            health = client.get("/healthz")
            missing_nia = client.post("/nia/chat", json={})
            disabled = client.post(INSTALLATION_CALLBACK_PATH, data={})

        self.assertEqual(health.status_code, 200)
        self.assertEqual(
            health.json(),
            {
                "status": "ok",
                "service": "bitrix_oauth_installation",
                "effective_mode": "off",
                "activation_locked": True,
                "external_calls_enabled": False,
                "installation_enabled": False,
                "pilot_enabled": False,
                "pilot_emergency_stop": True,
            },
        )
        self.assertEqual(missing_nia.status_code, 404)
        self.assertEqual(disabled.status_code, 503)
        self.assertEqual(
            disabled.json()["reason"],
            "installation_route_disabled",
        )

    def test_accepts_cloudflare_quick_tunnel_host(self):
        settings = load_settings({})
        app = create_installation_entrypoint(settings_loader=lambda: settings)

        with TestClient(
            app,
            base_url="https://random.trycloudflare.com",
        ) as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)

    def test_rejects_untrusted_host(self):
        settings = load_settings({})
        app = create_installation_entrypoint(settings_loader=lambda: settings)

        with TestClient(app, base_url="https://attacker.invalid") as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
