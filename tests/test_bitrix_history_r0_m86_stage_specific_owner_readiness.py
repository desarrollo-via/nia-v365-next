import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_owner_readiness import (
    audit_m86av_readiness,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AUAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_real_owner import (
    M86AVStageSpecificRealOwner,
)


class M86AVStageSpecificOwnerReadinessTests(unittest.TestCase):
    def test_readiness_does_not_call_real_factory_reference(self):
        calls = []
        result = audit_m86av_readiness(
            owner=M86AVStageSpecificRealOwner(
                source_factory=lambda: calls.append("forbidden")
            ),
            authorization=M86AUAuthorizationContract(),
        )
        self.assertEqual(
            (result.state, calls),
            ("READY-TO-SHOW-STAGE-AUTHORIZATION", []),
        )
        self.assertTrue(result.owner_dormant)
        self.assertTrue(result.one_shot_execution_bound)
        self.assertTrue(result.real_factory_bound)

    def test_literal_remains_unshown_and_unreceived(self):
        result = audit_m86av_readiness(
            owner=M86AVStageSpecificRealOwner(source_factory=lambda: None),
            authorization=M86AUAuthorizationContract(),
        )
        self.assertTrue(result.literal_prepared)
        self.assertFalse(result.literal_shown)
        self.assertFalse(result.authorization_received)
        self.assertFalse(result.execution_surface_has_cli)

    def test_all_real_and_external_counts_remain_zero(self):
        result = audit_m86av_readiness(
            owner=M86AVStageSpecificRealOwner(source_factory=lambda: None),
            authorization=M86AUAuthorizationContract(),
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
            audit_m86av_readiness(
                owner=object(), authorization=M86AUAuthorizationContract()
            ).state,
            "NO-GO",
        )
        self.assertEqual(
            audit_m86av_readiness(
                owner=M86AVStageSpecificRealOwner(source_factory=lambda: None),
                authorization=object(),
            ).state,
            "NO-GO",
        )


if __name__ == "__main__":
    unittest.main()
