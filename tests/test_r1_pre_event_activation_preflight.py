import unittest
from pathlib import Path

from bitrix_connector.r1_pre_event_activation_preflight import (
    DEPLOYED_MERGE_SHA,
    DEPLOYED_TREE_SHA,
    EXPECTED_BASELINE_VALUES,
    PROTECTED_TARGET_ID,
    PROTECTED_SOURCE_KIND,
    SWITCH_ORDER,
    R1ActivationPreflightEvidence,
    SanitizedSwitchBaseline,
    audit_r1_activation_preflight,
)


ROOT = Path(__file__).resolve().parents[1]


def switches(*, present=True):
    return tuple(
        SanitizedSwitchBaseline(
            name=name,
            present=present,
            value=EXPECTED_BASELINE_VALUES[name] if present else None,
        )
        for name in SWITCH_ORDER
    )


def evidence(**changes):
    values = {
        "deployed_sha": DEPLOYED_MERGE_SHA,
        "deployed_tree": DEPLOYED_TREE_SHA,
        "workflow_success": True,
        "dormant_health_verified": True,
        "full_tests_passed": True,
        "host_supports_protected_source": True,
        "protected_source_kind": PROTECTED_SOURCE_KIND,
        "protected_target_id": PROTECTED_TARGET_ID,
        "protected_record_shape_verified": True,
        "protected_setting_count": 7,
        "credential_read_calls": 1,
        "oauth_read_calls": 1,
        "refresh_calls": 0,
        "retry_calls": 0,
        "resources_closed": True,
        "review_auth_configured": True,
        "switches": switches(),
        "deal_id": 614949,
        "chat_id": 78733,
        "dialog_id": "chat78733",
        "bot_nia_absent": True,
        "bot_next_absent": True,
    }
    values.update(changes)
    return R1ActivationPreflightEvidence(**values)


class R1ActivationPreflightTests(unittest.TestCase):
    def test_exact_sanitized_evidence_is_ready_but_not_authorized(self):
        result = audit_r1_activation_preflight(evidence())

        self.assertEqual(result.state, "READY-FIRST-CONFIRMATION")
        self.assertTrue(result.deployment_verified)
        self.assertTrue(result.protected_source_verified)
        self.assertTrue(result.review_auth_verified)
        self.assertTrue(result.switch_baseline_verified)
        self.assertTrue(result.participant_baseline_verified)
        self.assertFalse(result.activation_authorized)
        self.assertEqual(result.evaluator_private_reads, 0)
        self.assertEqual(result.evaluator_external_calls, 0)
        self.assertEqual(result.evaluator_mutations, 0)

    def test_present_switches_have_literal_rollback_values(self):
        result = audit_r1_activation_preflight(evidence())

        self.assertEqual(
            result.rollback_plan,
            tuple(
                f"restore-value:{name}={EXPECTED_BASELINE_VALUES[name]}"
                for name in SWITCH_ORDER
            ),
        )

    def test_absent_switches_restore_absence(self):
        result = audit_r1_activation_preflight(
            evidence(switches=switches(present=False))
        )

        self.assertEqual(result.state, "READY-FIRST-CONFIRMATION")
        self.assertEqual(
            result.rollback_plan,
            tuple(f"restore-absence:{name}" for name in SWITCH_ORDER),
        )

    def test_mixed_exact_switch_baseline_is_reversible(self):
        mixed = tuple(
            SanitizedSwitchBaseline(
                name=name,
                present=index != 1,
                value=EXPECTED_BASELINE_VALUES[name] if index != 1 else None,
            )
            for index, name in enumerate(SWITCH_ORDER)
        )
        result = audit_r1_activation_preflight(evidence(switches=mixed))

        self.assertEqual(result.state, "READY-FIRST-CONFIRMATION")
        self.assertIn(f"restore-absence:{SWITCH_ORDER[1]}", result.rollback_plan)

    def test_any_protected_source_drift_is_no_go(self):
        cases = (
            {"host_supports_protected_source": False},
            {"protected_source_kind": "windows-credential-manager"},
            {"protected_target_id": "wrong-target"},
            {"protected_record_shape_verified": False},
            {"protected_setting_count": 6},
            {"credential_read_calls": 0},
            {"oauth_read_calls": 0},
            {"refresh_calls": 1},
            {"retry_calls": 1},
            {"resources_closed": False},
            {"secret_values_exposed": True},
        )
        for change in cases:
            with self.subTest(change=change):
                result = audit_r1_activation_preflight(evidence(**change))
                self.assertEqual(result.state, "NO-GO")
                self.assertFalse(result.activation_authorized)
                self.assertEqual(result.rollback_plan, ())

    def test_switch_drift_or_ambiguity_is_no_go(self):
        cases = (
            switches()[:-1],
            tuple(reversed(switches())),
            (
                *switches()[:2],
                SanitizedSwitchBaseline(
                    name=SWITCH_ORDER[2], present=True, value="pre-event"
                ),
            ),
            (
                SanitizedSwitchBaseline(
                    name=SWITCH_ORDER[0], present=False, value="false"
                ),
                *switches()[1:],
            ),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                result = audit_r1_activation_preflight(
                    evidence(switches=candidate)
                )
                self.assertEqual(result.state, "NO-GO")
                self.assertEqual(result.rollback_plan, ())

    def test_scope_or_deployment_drift_is_no_go(self):
        cases = (
            {"deployed_sha": "0" * 40},
            {"deployed_tree": "0" * 40},
            {"workflow_success": False},
            {"dormant_health_verified": False},
            {"full_tests_passed": False},
            {"review_auth_configured": False},
            {"deal_id": 1},
            {"chat_id": 1},
            {"dialog_id": "chat1"},
            {"bot_nia_absent": False},
            {"bot_next_absent": False},
        )
        for change in cases:
            with self.subTest(change=change):
                self.assertEqual(
                    audit_r1_activation_preflight(evidence(**change)).state,
                    "NO-GO",
                )

    def test_module_has_no_execution_or_private_source_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "r1_pre_event_activation_preflight.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "dotenv",
            "ctypes.",
            "credread",
            "get_access_token",
            "fetch_exact",
            "httpx",
            "requests",
            "subprocess",
            "argparse",
            "print(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
