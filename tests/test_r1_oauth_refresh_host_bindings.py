import os
import unittest
from unittest.mock import patch

from bitrix_connector.r1_oauth_refresh_host_bindings import (
    R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST,
    build_r1_oauth_refresh_host_bindings,
)


class R1OAuthRefreshHostBindingsTests(unittest.TestCase):
    def test_missing_allowlist_value_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            result = build_r1_oauth_refresh_host_bindings()
        self.assertIsNone(result.bindings)
        self.assertEqual(result.reason, "configuration_missing")

    def test_exact_allowlist_builds_without_owner(self):
        values = {
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[0]: "https://login.microsoftonline.com/01234567-89ab-cdef-0123-456789abcdef/v2.0",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[1]: "api://r1-audience",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[2]: "host-client-id",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[3]: "https://login.microsoftonline.com/tenant/discovery/v2.0/keys",
        }
        with patch.dict(os.environ, values, clear=True):
            result = build_r1_oauth_refresh_host_bindings()
        self.assertEqual(result.reason, "ready")
        self.assertIsNotNone(result.bindings)
        self.assertEqual(result.bindings.policy.audience, "api://r1-audience")
        self.assertEqual(
            result.bindings.policy.alternate_issuer,
            "https://sts.windows.net/01234567-89ab-cdef-0123-456789abcdef/",
        )
        self.assertTrue(result.bindings.policy.allow_appid_client_claim)
        self.assertEqual(result.bindings.policy.maximum_token_age_seconds, 86_400)
        self.assertTrue(callable(result.post_write_close_executor))

    def test_non_tenant_v2_issuer_fails_closed(self):
        values = {
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[0]: "issuer-fixture",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[1]: "api://r1-audience",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[2]: "host-client-id",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[3]: "https://login.microsoftonline.com/tenant/discovery/v2.0/keys",
        }
        with patch.dict(os.environ, values, clear=True):
            result = build_r1_oauth_refresh_host_bindings()
        self.assertIsNone(result.bindings)
        self.assertEqual(result.reason, "issuer_rejected")


if __name__ == "__main__":
    unittest.main()
