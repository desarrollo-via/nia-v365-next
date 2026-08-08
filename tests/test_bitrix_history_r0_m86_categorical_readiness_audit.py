import unittest

from bitrix_connector.bitrix_history_r0_m86_categorical_probe_authorization import (
    M86AOAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_m86_categorical_readiness_audit import (
    audit_m86ap_readiness,
)
from bitrix_connector.bitrix_history_r0_m86_dormant_real_categorical_owner import (
    M86ANDormantRealCategoricalOwner,
)


class M86APCategoricalReadinessAuditTests(unittest.TestCase):
    def test_ready_to_show_does_not_call_factory(self):
        calls = []
        owner = M86ANDormantRealCategoricalOwner(
            source_factory=lambda: calls.append("forbidden")
        )
        result = audit_m86ap_readiness(
            owner=owner,
            authorization=M86AOAuthorizationContract(),
        )
        self.assertEqual(result.state, "READY-TO-SHOW-AUTHORIZATION")
        self.assertEqual(calls, [])
        self.assertTrue(result.owner_dormant)
        self.assertTrue(result.real_factory_bound)

    def test_literal_remains_unshown_and_unreceived(self):
        result = audit_m86ap_readiness(
            owner=M86ANDormantRealCategoricalOwner(source_factory=lambda: None),
            authorization=M86AOAuthorizationContract(),
        )
        self.assertTrue(result.literal_prepared)
        self.assertFalse(result.literal_shown)
        self.assertFalse(result.authorization_received)

    def test_all_real_and_external_counts_remain_zero(self):
        result = audit_m86ap_readiness(
            owner=M86ANDormantRealCategoricalOwner(source_factory=lambda: None),
            authorization=M86AOAuthorizationContract(),
        )
        self.assertEqual(
            (result.real_factory_calls, result.real_read_calls, result.external_calls),
            (0, 0, 0),
        )
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_wrong_contracts_fail_closed(self):
        self.assertEqual(
            audit_m86ap_readiness(
                owner=object(), authorization=M86AOAuthorizationContract()
            ).state,
            "NO-GO",
        )
        self.assertEqual(
            audit_m86ap_readiness(
                owner=M86ANDormantRealCategoricalOwner(source_factory=lambda: None),
                authorization=object(),
            ).state,
            "NO-GO",
        )


if __name__ == "__main__":
    unittest.main()
