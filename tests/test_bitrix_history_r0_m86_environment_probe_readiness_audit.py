import unittest

from bitrix_connector.bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantBindingContract,
)
from bitrix_connector.bitrix_history_r0_m86_environment_probe_authorization import (
    M86AFAuthorizationContract,
)
from bitrix_connector.bitrix_history_r0_m86_environment_probe_readiness_audit import (
    audit_m86ag_readiness,
)


class M86AGReadinessAuditTests(unittest.TestCase):
    def test_contracts_are_ready_only_to_show_authorization(self):
        result = audit_m86ag_readiness(
            binding=M86AEDormantBindingContract(),
            authorization=M86AFAuthorizationContract(),
        )
        self.assertEqual(
            (result.state, result.failure_category),
            ("READY-TO-SHOW-AUTHORIZATION", "none"),
        )
        self.assertTrue(result.binding_defined)
        self.assertTrue(result.binding_dormant)
        self.assertTrue(result.literal_frozen)

    def test_readiness_does_not_mean_authorized_or_executable(self):
        result = audit_m86ag_readiness(
            binding=M86AEDormantBindingContract(),
            authorization=M86AFAuthorizationContract(),
        )
        self.assertFalse(result.execution_surface_present)
        self.assertFalse(result.authorization_received)
        self.assertEqual(
            (
                result.source_read_calls,
                result.operating_system_calls,
                result.external_calls,
                result.target_write_calls,
            ),
            (0, 0, 0, 0),
        )

    def test_wrong_contracts_fail_closed(self):
        bad_binding = audit_m86ag_readiness(
            binding=object(),
            authorization=M86AFAuthorizationContract(),
        )
        bad_literal = audit_m86ag_readiness(
            binding=M86AEDormantBindingContract(),
            authorization=object(),
        )
        self.assertEqual(bad_binding.failure_category, "binding_contract_invalid")
        self.assertEqual(bad_literal.failure_category, "literal_contract_invalid")

    def test_production_barriers_remain_intact(self):
        result = audit_m86ag_readiness(
            binding=M86AEDormantBindingContract(),
            authorization=M86AFAuthorizationContract(),
        )
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)


if __name__ == "__main__":
    unittest.main()
