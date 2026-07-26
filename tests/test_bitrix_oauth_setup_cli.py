import io
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from bitrix_connector import oauth_setup_cli


class OAuthSetupCliTests(unittest.TestCase):
    def setUp(self):
        project_root = Path(__file__).resolve().parent.parent
        self.env_path = project_root / (
            f".oauth-setup-test-{uuid.uuid4().hex}.env"
        )
        self.addCleanup(self.env_path.unlink, missing_ok=True)
        self.env_path.write_text(
            "NIA_BITRIX_MODE=off\n"
            "NIA_BITRIX_MONGO_URI=\n"
            "NIA_BITRIX_MONGO_DB=\n"
            "NIA_BITRIX_CLIENT_ID=\n"
            "NIA_BITRIX_CLIENT_SECRET=\n",
            encoding="utf-8",
        )

    def test_configures_storage_without_printing_uri(self):
        secret = "mongodb+srv://user:private@cluster.invalid/"
        output = io.StringIO()
        with (
            patch.object(oauth_setup_cli, "ENV_PATH", self.env_path),
            patch("getpass.getpass", return_value=secret),
            patch("builtins.input", return_value="nia_bitrix"),
            redirect_stdout(output),
        ):
            result = oauth_setup_cli.main(["configure-storage"])

        values = dotenv_values(self.env_path)
        self.assertEqual(result, 0)
        self.assertEqual(values["NIA_BITRIX_MONGO_URI"], secret)
        self.assertEqual(values["NIA_BITRIX_MONGO_DB"], "nia_bitrix")
        self.assertNotIn(secret, output.getvalue())

    def test_configures_client_without_printing_credentials(self):
        answers = iter(("local.abc123", "private-client-secret"))
        output = io.StringIO()
        with (
            patch.object(oauth_setup_cli, "ENV_PATH", self.env_path),
            patch("getpass.getpass", side_effect=lambda _: next(answers)),
            redirect_stdout(output),
        ):
            result = oauth_setup_cli.main(["configure-client"])

        values = dotenv_values(self.env_path)
        self.assertEqual(result, 0)
        self.assertEqual(values["NIA_BITRIX_CLIENT_ID"], "local.abc123")
        self.assertEqual(
            values["NIA_BITRIX_CLIENT_SECRET"],
            "private-client-secret",
        )
        self.assertNotIn("local.abc123", output.getvalue())
        self.assertNotIn("private-client-secret", output.getvalue())

    def test_rejects_invalid_uri_without_changing_file(self):
        before = self.env_path.read_bytes()
        with (
            patch.object(oauth_setup_cli, "ENV_PATH", self.env_path),
            patch("getpass.getpass", return_value="https://invalid.test"),
        ):
            result = oauth_setup_cli.main(["configure-storage"])

        self.assertEqual(result, 2)
        self.assertEqual(self.env_path.read_bytes(), before)

    def test_preflight_reports_only_safe_state_and_closes_resources(self):
        self.env_path.write_text(
            self.env_path.read_text(encoding="utf-8")
            + "NIA_BITRIX_DOMAIN=portal.bitrix24.test\n"
            + "NIA_BITRIX_MONGO_URI=mongodb://user:private@mongo.invalid/\n"
            + "NIA_BITRIX_MONGO_DB=nia\n",
            encoding="utf-8",
        )

        class Resources:
            closed = False

            async def close(self):
                self.closed = True

        class Factory:
            def __init__(self):
                self.resources = Resources()
                self.settings = None

            async def build(self, settings):
                self.settings = settings
                return self.resources

        factory = Factory()
        output = io.StringIO()
        with (
            patch.object(oauth_setup_cli, "ENV_PATH", self.env_path),
            redirect_stdout(output),
        ):
            result = __import__("asyncio").run(
                oauth_setup_cli._preflight_storage(factory)
            )

        payload = __import__("json").loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(factory.resources.closed)
        self.assertEqual(factory.settings.effective_mode.value, "off")
        self.assertTrue(factory.settings.activation_locked)
        self.assertFalse(factory.settings.external_calls_enabled)
        self.assertNotIn("private", output.getvalue())

    def test_installation_status_prints_only_safe_projection(self):
        from bitrix_connector.installation_status import (
            OAuthInstallationStatusResponse,
        )

        self.env_path.write_text(
            self.env_path.read_text(encoding="utf-8")
            + "NIA_BITRIX_DOMAIN=portal.bitrix24.test\n"
            + "NIA_BITRIX_MONGO_URI=mongodb://user:private@mongo.invalid/\n"
            + "NIA_BITRIX_MONGO_DB=nia\n",
            encoding="utf-8",
        )

        class Service:
            async def get_status(self, domain):
                self.domain = domain
                return OAuthInstallationStatusResponse(
                    status="installed",
                    installation_present=True,
                    access_token_present=True,
                    refresh_token_present=True,
                    application_token_present=True,
                    revision=1,
                )

        class Resources:
            def __init__(self):
                self.service = Service()
                self.closed = False

            async def close(self):
                self.closed = True

        class Factory:
            def __init__(self):
                self.resources = Resources()

            async def build(self, settings):
                return self.resources

        factory = Factory()
        output = io.StringIO()
        with (
            patch.object(oauth_setup_cli, "ENV_PATH", self.env_path),
            redirect_stdout(output),
        ):
            result = __import__("asyncio").run(
                oauth_setup_cli._installation_status(factory)
            )

        payload = __import__("json").loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(factory.resources.closed)
        self.assertEqual(payload["status"], "installed")
        self.assertNotIn("private", output.getvalue())

    def test_syncs_identity_without_printing_application_token(self):
        from datetime import datetime, timedelta, timezone

        from bitrix_connector.oauth import BitrixOAuthInstallation

        self.env_path.write_text(
            self.env_path.read_text(encoding="utf-8")
            + "NIA_BITRIX_DOMAIN=portal.bitrix24.test\n"
            + "NIA_BITRIX_MEMBER_ID=\n"
            + "NIA_BITRIX_APPLICATION_TOKEN=\n",
            encoding="utf-8",
        )
        now = datetime.now(timezone.utc)
        installation = BitrixOAuthInstallation(
            member_id="member-private",
            domain="portal.bitrix24.test",
            client_endpoint="https://portal.bitrix24.test/rest",
            server_endpoint="https://oauth.bitrix.info/rest",
            access_token="access-private",
            refresh_token="refresh-private",
            application_token="application-private",
            expires_at=now + timedelta(hours=1),
            updated_at=now,
        )

        class Store:
            async def get_installation_by_domain(self, domain):
                self.domain = domain
                return installation

        output = io.StringIO()
        with (
            patch.object(oauth_setup_cli, "ENV_PATH", self.env_path),
            redirect_stdout(output),
        ):
            result = __import__("asyncio").run(
                oauth_setup_cli._sync_installation_identity(Store())
            )

        values = dotenv_values(self.env_path)
        self.assertEqual(result, 0)
        self.assertEqual(values["NIA_BITRIX_MEMBER_ID"], "member-private")
        self.assertEqual(
            values["NIA_BITRIX_APPLICATION_TOKEN"],
            "application-private",
        )
        self.assertNotIn("member-private", output.getvalue())
        self.assertNotIn("application-private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
