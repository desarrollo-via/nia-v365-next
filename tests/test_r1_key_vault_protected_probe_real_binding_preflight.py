import unittest

from bitrix_connector.r1_key_vault_protected_probe_real_binding_preflight import (
    inspect_protected_probe_real_binding,
)


class R1KeyVaultProtectedProbeRealBindingPreflightTests(unittest.TestCase):
    def test_preflight_stops_only_on_unresolved_exact_source(self):
        result = inspect_protected_probe_real_binding()
        self.assertEqual(result.state, "NO-GO-SOURCE-DECISION-REQUIRED")
        self.assertEqual(result.reason, "protected_review_token_source_unresolved")
        self.assertEqual(result.review_token_name, "NIA_BITRIX_REVIEW_TOKEN")
        self.assertFalse(result.existing_r1_target_contains_review_token)
        self.assertIsNone(result.source_target_id)
        self.assertFalse(result.source_binding_ready)
        self.assertTrue(result.transport_binding_ready)
        self.assertFalse(result.execution_ready)

    def test_preflight_is_inert_and_bounded(self):
        result = inspect_protected_probe_real_binding()
        self.assertEqual(
            (result.request_budget, result.retry_budget, result.redirect_budget),
            (1, 0, 0),
        )
        self.assertEqual(result.timeout_seconds, 15)
        self.assertFalse(result.source_opened)
        self.assertFalse(result.token_materialized)
        self.assertEqual(result.external_calls, 0)


if __name__ == "__main__":
    unittest.main()
