import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_authorization_readiness import (
    audit_m86au_readiness,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_dormant_real_owner import (
    M86ATStageSpecificDormantRealOwner,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AUAuthorizationContract,
)


class M86AUStageSpecificAuthorizationReadinessTests(unittest.TestCase):
    def test_readiness_does_not_call_real_factory_reference(self):
        calls = []
        result = audit_m86au_readiness(
            owner=M86ATStageSpecificDormantRealOwner(
                source_factory=lambda: calls.append("forbidden")
            ),
            authorization=M86AUAuthorizationContract(),
        )
        self.assertEqual(
            (result.state, calls),
            ("READY-TO-SHOW-STAGE-AUTHORIZATION", []),
        )
        self.assertTrue(result.categories_frozen)
        self.assertTrue(result.owner_dormant)
        self.assertTrue(result.real_factory_bound)

    def test_literal_remains_unshown_unreceived_and_unlinked(self):
        result = audit_m86au_readiness(
            owner=M86ATStageSpecificDormantRealOwner(source_factory=lambda: None),
            authorization=M86AUAuthorizationContract(),
        )
        self.assertTrue(result.literal_prepared)
        self.assertFalse(result.literal_shown)
        self.assertFalse(result.authorization_received)
        self.assertFalse(result.linked_to_execution)
        self.assertFalse(result.execution_surface_available)

    def test_all_real_and_external_counts_remain_zero(self):
        result = audit_m86au_readiness(
            owner=M86ATStageSpecificDormantRealOwner(source_factory=lambda: None),
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
            audit_m86au_readiness(
                owner=object(), authorization=M86AUAuthorizationContract()
            ).state,
            "NO-GO",
        )
        self.assertEqual(
            audit_m86au_readiness(
                owner=M86ATStageSpecificDormantRealOwner(source_factory=lambda: None),
                authorization=object(),
            ).state,
            "NO-GO",
        )


if __name__ == "__main__":
    unittest.main()
