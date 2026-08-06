import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_fixture_owner import (
    M86ASStageSpecificFixtureOwner,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_readiness_audit import (
    audit_m86as_readiness,
)


class M86ASStageSpecificReadinessAuditTests(unittest.TestCase):
    def test_readiness_does_not_call_fixture_factory(self):
        calls = []
        result = audit_m86as_readiness(
            owner=M86ASStageSpecificFixtureOwner(
                source_factory=lambda: calls.append("forbidden")
            )
        )
        self.assertEqual((result.state, calls), ("READY-HERMETIC", []))
        self.assertTrue(result.categories_frozen)
        self.assertTrue(result.fixture_owner_dormant)

    def test_readiness_has_zero_real_or_external_activity(self):
        result = audit_m86as_readiness(
            owner=M86ASStageSpecificFixtureOwner(source_factory=lambda: None)
        )
        self.assertEqual(
            (result.fixture_factory_calls, result.real_read_calls, result.external_calls),
            (0, 0, 0),
        )
        self.assertFalse(result.real_source_bound)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_wrong_owner_fails_closed(self):
        self.assertEqual(audit_m86as_readiness(owner=object()).state, "NO-GO")


if __name__ == "__main__":
    unittest.main()
