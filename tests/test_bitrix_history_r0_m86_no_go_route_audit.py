import unittest

from bitrix_connector.bitrix_history_r0_m86_no_go_route_audit import (
    M86AKRouteAudit,
    M86AK_NO_GO_ROUTES,
)


class M86AKNoGoRouteAuditTests(unittest.TestCase):
    def test_all_internal_stages_are_mapped_once(self):
        audit = M86AKRouteAudit()
        stages = tuple(route.internal_stage for route in audit.routes)
        self.assertEqual(len(stages), 8)
        self.assertEqual(len(set(stages)), 8)

    def test_source_failures_collapse_to_one_aggregate_category(self):
        categories = {
            route.public_category
            for route in M86AK_NO_GO_ROUTES
            if route.internal_stage.startswith("source_")
        }
        self.assertEqual(categories, {"source_aggregate_unavailable"})

    def test_routes_reveal_no_individual_evidence(self):
        for route in M86AK_NO_GO_ROUTES:
            self.assertFalse(route.reveals_individual_key)
            self.assertFalse(route.reveals_value)
            self.assertFalse(route.reveals_length)
            self.assertFalse(route.reveals_progress_count)

    def test_audit_is_inert_after_consumed_probe(self):
        audit = M86AKRouteAudit()
        self.assertEqual((audit.state, audit.current_real_read_budget), ("MAPPED-INERT", 0))
        self.assertFalse(audit.real_probe_authorized)
        self.assertFalse(audit.real_probe_executed)
        self.assertEqual(audit.external_calls, 0)


if __name__ == "__main__":
    unittest.main()
