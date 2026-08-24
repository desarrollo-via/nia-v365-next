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
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[0]: "https://login.microsoftonline.com/tenant/v2.0",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[1]: "api://r1-audience",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[2]: "host-client-id",
            R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST[3]: "https://login.microsoftonline.com/tenant/discovery/v2.0/keys",
        }
        with patch.dict(os.environ, values, clear=True):
            result = build_r1_oauth_refresh_host_bindings()
        self.assertEqual(result.reason, "ready")
        self.assertIsNotNone(result.bindings)
        self.assertEqual(result.bindings.policy.audience, "api://r1-audience")


if __name__ == "__main__":
    unittest.main()
