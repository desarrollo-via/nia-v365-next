import unittest

from bitrix_connector.config import ConnectorMode, load_settings
from bitrix_connector.mode_policy import (
    ExternalAction,
    ExternalCallPolicy,
)


class ExternalCallPolicyTests(unittest.TestCase):
    def policy(self, mode, *, locked=False, enabled=True):
        return ExternalCallPolicy(
            effective_mode=mode,
            activation_locked=locked,
            external_calls_enabled=enabled,
        )

    def test_real_settings_remain_locked_even_when_active_is_requested(self):
        policy = ExternalCallPolicy.from_settings(
            load_settings({"NIA_BITRIX_MODE": "active"})
        )

        self.assertFalse(policy.authorize(ExternalAction.NIA).allowed)
        self.assertFalse(policy.authorize(ExternalAction.BITRIX).allowed)
        self.assertEqual(
            policy.authorize(ExternalAction.NIA).reason,
            "connector_activation_locked",
        )

    def test_nia_base_url_is_optional_and_trimmed_without_enabling_calls(self):
        empty = load_settings({})
        configured = load_settings({"NIA_BASE_URL": "  http://nia-next:8000/  "})

        self.assertIsNone(empty.nia_base_url)
        self.assertEqual(configured.nia_base_url, "http://nia-next:8000/")
        self.assertFalse(configured.external_calls_enabled)

    def test_review_allows_both_guarded_calls(self):
        policy = self.policy(ConnectorMode.REVIEW)

        self.assertTrue(policy.authorize(ExternalAction.NIA).allowed)
        self.assertTrue(policy.authorize(ExternalAction.BITRIX).allowed)

    def test_shadow_allows_nia_and_blocks_bitrix(self):
        policy = self.policy(ConnectorMode.SHADOW)

        self.assertTrue(policy.authorize(ExternalAction.NIA).allowed)
        decision = policy.authorize(ExternalAction.BITRIX)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "connector_shadow_blocks_bitrix")

    def test_active_still_requires_external_switch(self):
        policy = self.policy(ConnectorMode.ACTIVE, enabled=False)

        self.assertEqual(
            policy.authorize(ExternalAction.NIA).reason,
            "connector_external_calls_disabled",
        )
        self.assertFalse(policy.authorize(ExternalAction.BITRIX).allowed)


if __name__ == "__main__":
    unittest.main()
