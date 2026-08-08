import unittest
from pathlib import Path

from bitrix_connector.bitrix_oauth_refresh_rollback_readiness import (
    OAuthRefreshRollbackEvidence,
    audit_current_oauth_refresh_owner,
    audit_oauth_refresh_rollback_readiness,
)


ROOT = Path(__file__).resolve().parents[1]


class OAuthRefreshRollbackReadinessTests(unittest.TestCase):
    def test_current_owner_is_blocked_without_exact_external_rollback(self):
        result = audit_current_oauth_refresh_owner()

        self.assertEqual(result.state, "DO-NOT-REQUEST")
        self.assertTrue(result.conditional_persistence_verified)
        self.assertTrue(result.persistence_readback_verified)
        self.assertFalse(result.exact_rollback_available)
        self.assertFalse(result.local_restore_safe)
        self.assertTrue(result.two_confirmations_required)
        self.assertFalse(result.first_confirmation_ready)
        self.assertFalse(result.second_confirmation_ready)
        self.assertEqual(
            (
                result.external_calls,
                result.source_open_calls,
                result.oauth_refresh_calls,
                result.mongo_read_calls,
                result.mongo_write_calls,
                result.bitrix_calls,
            ),
            (0, 0, 0, 0, 0, 0),
        )

    def test_only_exact_reversible_evidence_can_prepare_first_confirmation(self):
        result = audit_oauth_refresh_rollback_readiness(
            OAuthRefreshRollbackEvidence(
                refresh_rotates_external_pair=True,
                conditional_persistence=True,
                persistence_readback=True,
                provider_rollback_endpoint_available=True,
                previous_pair_valid_after_rotation=True,
            )
        )

        self.assertEqual(
            result.state,
            "READY-TO-PREPARE-FIRST-CONFIRMATION",
        )
        self.assertTrue(result.exact_rollback_available)
        self.assertTrue(result.local_restore_safe)
        self.assertTrue(result.first_confirmation_ready)
        self.assertFalse(result.second_confirmation_ready)

    def test_local_restore_without_provider_rollback_remains_blocked(self):
        result = audit_oauth_refresh_rollback_readiness(
            OAuthRefreshRollbackEvidence(
                refresh_rotates_external_pair=True,
                conditional_persistence=True,
                persistence_readback=True,
                provider_rollback_endpoint_available=False,
                previous_pair_valid_after_rotation=True,
            )
        )

        self.assertEqual(result.state, "DO-NOT-REQUEST")
        self.assertFalse(result.exact_rollback_available)
        self.assertFalse(result.local_restore_safe)

    def test_module_has_no_source_network_mongo_or_command_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_oauth_refresh_rollback_readiness.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env",
            "allowlisteddotenvsource",
            "httpx",
            "motor",
            "pymongo",
            "refresh_access_token(",
            "update_one(",
            "subprocess",
            "socket",
            "argparse",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
