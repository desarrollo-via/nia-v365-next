import unittest

from bitrix_connector.bitrix_event_scoped_r1_deployment_readiness import (
    EventScopedR1DeploymentEvidence,
    audit_current_local_dormant_mount,
    audit_event_scoped_r1_deployment,
)


class EventScopedR1DeploymentReadinessTests(unittest.TestCase):
    def test_current_mount_is_local_verified_but_not_deployable(self):
        result = audit_current_local_dormant_mount()
        self.assertEqual(result.state, "LOCAL-DORMANT-VERIFIED")
        self.assertTrue(result.dormant_mount_verified)
        self.assertTrue(result.activation_impossible_from_configuration)
        self.assertFalse(result.dependency_cut_frozen)
        self.assertFalse(result.deployment_ready)
        self.assertFalse(result.deployment_authorized)
        self.assertFalse(result.exact_rollback_target_available)
        self.assertEqual((result.external_calls, result.git_writes, result.azure_writes), (0, 0, 0))

    def test_exact_target_needs_cut_commit_and_verified_production_base(self):
        base = dict(
            integrated_mount_present=True,
            observer_is_none=True,
            activation_surface_absent=True,
            focal_tests_passed=True,
            full_tests_passed=True,
            dependency_cut_frozen=True,
            deployment_commit_sha="a" * 40,
        )
        self.assertFalse(
            audit_event_scoped_r1_deployment(
                EventScopedR1DeploymentEvidence(**base)
            ).exact_rollback_target_available
        )
        base["production_base_sha_verified"] = True
        ready_target = audit_event_scoped_r1_deployment(
            EventScopedR1DeploymentEvidence(**base)
        )
        self.assertTrue(ready_target.exact_rollback_target_available)
        self.assertFalse(ready_target.deployment_ready)
        self.assertTrue(ready_target.dependency_cut_frozen)

    def test_frozen_cut_is_visible_without_authorizing_deployment(self):
        result = audit_current_local_dormant_mount(dependency_cut_frozen=True)

        self.assertEqual(result.state, "LOCAL-DORMANT-VERIFIED")
        self.assertTrue(result.dependency_cut_frozen)
        self.assertFalse(result.deployment_ready)
        self.assertFalse(result.deployment_authorized)
        self.assertFalse(result.exact_rollback_target_available)

    def test_any_dormant_invariant_drift_is_no_go(self):
        result = audit_event_scoped_r1_deployment(
            EventScopedR1DeploymentEvidence(
                integrated_mount_present=True,
                observer_is_none=False,
                activation_surface_absent=True,
                focal_tests_passed=True,
                full_tests_passed=True,
                dependency_cut_frozen=False,
            )
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertFalse(result.dormant_mount_verified)


if __name__ == "__main__":
    unittest.main()
