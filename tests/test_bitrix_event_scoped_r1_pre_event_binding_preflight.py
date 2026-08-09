import unittest
from pathlib import Path

from bitrix_connector.bitrix_event_scoped_r1_pre_event_binding_preflight import (
    PRE_EVENT_BINDING_ALLOWED_STRATEGIES,
    PRE_EVENT_BINDING_DEFAULT_STRATEGY,
    PRE_EVENT_BINDING_MAX_WINDOW_SECONDS,
    PRE_EVENT_BINDING_LOCAL_TRACE_PATHS,
    PRE_EVENT_BINDING_PLANNED_PATHS,
    PRE_EVENT_BINDING_ROLLBACK,
    PRE_EVENT_BINDING_STRATEGY_SETTING,
    PreEventBindingPreflightEvidence,
    audit_pre_event_binding_preflight,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


def evidence(**changes):
    values = {
        "protected_factory_dormant": True,
        "router_binding_absent": True,
        "mount_accepts_injected_factory": True,
        "posterior_wrapper_mutually_excluded": True,
        "protected_allowlist_exact": True,
        "credential_read_budget_one": True,
        "oauth_read_budget_one": True,
        "refresh_budget_zero": True,
        "retry_budget_zero": True,
        "close_on_every_terminal_path": True,
        "planned_default_is_posterior": True,
        "planned_invalid_switch_fails_closed": True,
        "planned_paths": PRE_EVENT_BINDING_PLANNED_PATHS,
        "local_trace_paths": PRE_EVENT_BINDING_LOCAL_TRACE_PATHS,
        "candidate_path_count": 306,
        "candidate_path_digest": (
            "c4df72260a6bf6422e25b48b02e50957d652912643a7d7a476135fd6a8ac27b0"
        ),
        "focal_tests_passed": True,
        "full_tests_passed": True,
        "dependency_cut_frozen": True,
    }
    values.update(changes)
    return PreEventBindingPreflightEvidence(**values)


class PreEventBindingPreflightTests(unittest.TestCase):
    def test_exact_local_contract_is_prepared_but_not_authorized(self):
        result = audit_pre_event_binding_preflight(evidence())

        self.assertEqual(result.state, "LOCAL-PREFLIGHT-PREPARED")
        self.assertTrue(result.exact_scope_verified)
        self.assertTrue(result.protected_contract_verified)
        self.assertTrue(result.dormant_default_verified)
        self.assertTrue(result.rollback_contract_defined)
        self.assertFalse(result.exact_deployment_rollback_ready)
        self.assertFalse(result.critical_binding_authorized)
        self.assertEqual(result.private_reads, 0)
        self.assertEqual(result.mongo_calls, 0)
        self.assertEqual(result.oauth_reads, 0)
        self.assertEqual(result.bitrix_calls, 0)
        self.assertEqual(result.participant_mutations, 0)
        self.assertEqual(result.messages, 0)

    def test_scope_switch_allowlist_window_and_rollback_are_literal(self):
        result = audit_pre_event_binding_preflight(evidence())

        self.assertEqual(
            PRE_EVENT_BINDING_STRATEGY_SETTING,
            "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY",
        )
        self.assertEqual(PRE_EVENT_BINDING_DEFAULT_STRATEGY, "posterior")
        self.assertEqual(
            PRE_EVENT_BINDING_ALLOWED_STRATEGIES,
            ("posterior", "pre-event"),
        )
        self.assertEqual(PRE_EVENT_BINDING_MAX_WINDOW_SECONDS, 600)
        self.assertEqual(result.maximum_window_seconds, 600)
        self.assertEqual(result.protected_setting_count, len(PROTECTED_SETTING_NAMES))
        self.assertEqual(result.planned_path_count, 12)
        self.assertEqual(result.local_trace_path_count, 1)
        self.assertEqual(result.candidate_path_count, 306)
        self.assertEqual(PRE_EVENT_BINDING_LOCAL_TRACE_PATHS, ("nia_next.md",))
        self.assertNotIn("nia_next.md", PRE_EVENT_BINDING_PLANNED_PATHS)
        self.assertEqual(
            PRE_EVENT_BINDING_ROLLBACK,
            (
                "restore-source-to-exact-pre-binding-commit",
                "set-participant-strategy-to-posterior",
                "verify-r1-posterior-and-connector-off-locked-inert",
            ),
        )

    def test_any_contract_or_path_drift_is_no_go(self):
        cases = (
            {"protected_factory_dormant": False},
            {"router_binding_absent": False},
            {"protected_allowlist_exact": False},
            {"refresh_budget_zero": False},
            {"retry_budget_zero": False},
            {"close_on_every_terminal_path": False},
            {"planned_default_is_posterior": False},
            {"planned_invalid_switch_fails_closed": False},
            {"planned_paths": PRE_EVENT_BINDING_PLANNED_PATHS[:-1]},
            {"local_trace_paths": ()},
            {"candidate_path_count": 304},
            {"candidate_path_digest": "not-the-frozen-cut"},
            {"full_tests_passed": False},
            {"dependency_cut_frozen": False},
        )
        for change in cases:
            with self.subTest(change=change):
                result = audit_pre_event_binding_preflight(
                    evidence(**change)
                )
                self.assertEqual(result.state, "NO-GO")
                self.assertFalse(result.critical_binding_authorized)

    def test_exact_deployment_rollback_requires_sha_and_verified_base(self):
        without_base = audit_pre_event_binding_preflight(
            evidence(rollback_commit_sha="a" * 40)
        )
        exact = audit_pre_event_binding_preflight(
            evidence(
                rollback_commit_sha="a" * 40,
                production_base_verified=True,
            )
        )
        malformed = audit_pre_event_binding_preflight(
            evidence(
                rollback_commit_sha="not-a-sha",
                production_base_verified=True,
            )
        )

        self.assertFalse(without_base.exact_deployment_rollback_ready)
        self.assertTrue(exact.exact_deployment_rollback_ready)
        self.assertFalse(malformed.exact_deployment_rollback_ready)
        self.assertFalse(exact.critical_binding_authorized)

    def test_preflight_has_no_execution_or_private_source_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_event_scoped_r1_pre_event_binding_preflight.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "pilotdiscoveryoauthfactory",
            "windowscredential",
            "get_access_token",
            "fetch_exact",
            "os.environ",
            "dotenv",
            "httpx",
            "motor",
            "asyncio.run",
            "subprocess",
            "argparse",
            "print(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
