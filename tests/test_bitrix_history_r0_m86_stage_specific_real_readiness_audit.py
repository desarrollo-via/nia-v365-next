import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_dormant_real_owner import (
    M86ATStageSpecificDormantRealOwner,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_real_readiness_audit import (
    audit_m86at_readiness,
)


class M86ATStageSpecificRealReadinessAuditTests(unittest.TestCase):
    def test_readiness_does_not_call_real_factory_reference(self):
        calls = []
        result = audit_m86at_readiness(
            owner=M86ATStageSpecificDormantRealOwner(
                source_factory=lambda: calls.append("forbidden")
            )
        )
        self.assertEqual((result.state, calls), ("READY-TO-DESIGN-AUTHORIZATION", []))
        self.assertTrue(result.categories_reused)
        self.assertTrue(result.owner_dormant)
        self.assertTrue(result.real_factory_bound)

    def test_authorization_and_execution_remain_absent(self):
        result = audit_m86at_readiness(
            owner=M86ATStageSpecificDormantRealOwner(source_factory=lambda: None)
        )
        self.assertFalse(result.authorization_literal_prepared)
        self.assertFalse(result.authorization_received)
        self.assertFalse(result.execution_surface_available)
        self.assertFalse(result.execution_surface_has_cli)

    def test_all_real_and_external_counts_remain_zero(self):
        result = audit_m86at_readiness(
            owner=M86ATStageSpecificDormantRealOwner(source_factory=lambda: None)
        )
        self.assertEqual(
            (result.real_factory_calls, result.real_read_calls, result.external_calls),
            (0, 0, 0),
        )
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_wrong_owner_fails_closed(self):
        self.assertEqual(audit_m86at_readiness(owner=object()).state, "NO-GO")


if __name__ == "__main__":
    unittest.main()
