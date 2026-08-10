import unittest
from pathlib import Path

from bitrix_connector.r1_pre_event_activation_real_binding import (
    R1ActivationDormantRealBinding,
    R1ActivationRealOperations,
    _R1ActivationRealBindingPermit,
)
from bitrix_connector.r1_pre_event_activation_evidence_collector import (
    SanitizedDeploymentEvidence,
    SanitizedParticipantEvidence,
    SanitizedProtectedSourceEvidence,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    CONTROLLED_CHAT_ID,
    CONTROLLED_DEAL_ID,
    CONTROLLED_DIALOG_ID,
    DEPLOYED_MERGE_SHA,
    DEPLOYED_TREE_SHA,
    EXPECTED_BASELINE_VALUES,
    PROTECTED_SETTING_COUNT,
    PROTECTED_SOURCE_KIND,
    PROTECTED_TARGET_ID,
    SWITCH_ORDER,
    SanitizedSwitchBaseline,
)


ROOT = Path(__file__).resolve().parents[1]


def binding():
    calls = []

    async def deployment(**scope):
        calls.append(("deployment", scope))
        return SanitizedDeploymentEvidence(
            deployed_sha=DEPLOYED_MERGE_SHA,
            deployed_tree=DEPLOYED_TREE_SHA,
            workflow_success=True,
            dormant_health_verified=True,
            full_tests_passed=True,
        )

    async def protected_source(**scope):
        calls.append(("protected-source", scope))
        return SanitizedProtectedSourceEvidence(
            host_supports_protected_source=True,
            protected_source_kind=PROTECTED_SOURCE_KIND,
            protected_target_id=PROTECTED_TARGET_ID,
            protected_record_shape_verified=True,
            protected_setting_count=PROTECTED_SETTING_COUNT,
            credential_read_calls=1,
            oauth_read_calls=1,
            refresh_calls=0,
            retry_calls=0,
            resources_closed=True,
            review_auth_configured=True,
        )

    async def switches(**scope):
        calls.append(("switches", scope))
        return tuple(
            SanitizedSwitchBaseline(
                name=name,
                present=True,
                value=EXPECTED_BASELINE_VALUES[name],
            )
            for name in SWITCH_ORDER
        )

    async def participants(**scope):
        calls.append(("participants", scope))
        return SanitizedParticipantEvidence(
            deal_id=CONTROLLED_DEAL_ID,
            chat_id=CONTROLLED_CHAT_ID,
            dialog_id=CONTROLLED_DIALOG_ID,
            bot_nia_absent=True,
            bot_next_absent=True,
        )

    instance = R1ActivationDormantRealBinding(
        operations=R1ActivationRealOperations(
            deployment=deployment,
            protected_source=protected_source,
            switches=switches,
            participants=participants,
        )
    )
    return instance, calls


class R1ActivationRealBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_construction_is_dormant_and_authorizes_nothing(self):
        instance, calls = binding()

        preview = instance.preview()

        self.assertEqual(preview.state, "WAITING-EXACT-AUTHORIZATION")
        self.assertTrue(preview.gate_permit_required)
        self.assertFalse(preview.direct_build_allowed)
        self.assertFalse(preview.permit_consumed)
        self.assertEqual(preview.collector_constructions, 0)
        self.assertEqual(preview.operation_calls, 0)
        self.assertEqual(preview.external_calls, 0)
        self.assertEqual(preview.mutations, 0)
        self.assertFalse(preview.activation_authorized)
        self.assertEqual(calls, [])

    async def test_direct_build_is_blocked_without_calls(self):
        instance, calls = binding()

        with self.assertRaisesRegex(RuntimeError, "permit_required"):
            instance()

        self.assertEqual(calls, [])
        self.assertEqual(instance.preview().collector_constructions, 0)

    async def test_invalid_permit_fails_closed_without_calls(self):
        instance, calls = binding()

        with self.assertRaisesRegex(RuntimeError, "permit_invalid"):
            instance.build_after_gate_once(object())

        self.assertEqual(calls, [])
        self.assertEqual(instance.preview().collector_constructions, 0)

    async def test_hermetic_permit_builds_without_running_operations(self):
        instance, calls = binding()

        collector = instance.build_after_gate_once(
            _R1ActivationRealBindingPermit()
        )

        self.assertEqual(calls, [])
        preview = instance.preview()
        self.assertTrue(preview.permit_consumed)
        self.assertEqual(preview.collector_constructions, 1)
        self.assertEqual(preview.operation_calls, 0)
        self.assertFalse(preview.activation_authorized)
        self.assertIn("R1ActivationEvidenceCollector", type(collector).__name__)

    async def test_hermetic_operations_flow_only_after_collector_run(self):
        instance, calls = binding()
        collector = instance.build_after_gate_once(
            _R1ActivationRealBindingPermit()
        )

        result = await collector.collect()

        self.assertEqual(result.state, "EVIDENCE-COLLECTED")
        self.assertFalse(result.activation_authorized)
        self.assertEqual(
            [name for name, _scope in calls],
            ["deployment", "protected-source", "switches", "participants"],
        )

    async def test_binding_and_probes_are_one_shot(self):
        instance, calls = binding()
        collector = instance.build_after_gate_once(
            _R1ActivationRealBindingPermit()
        )
        await collector.collect()

        with self.assertRaisesRegex(RuntimeError, "reuse_or_permit_invalid"):
            instance.build_after_gate_once(_R1ActivationRealBindingPermit())
        repeated = await collector.collect()

        self.assertEqual(repeated.reason, "collector_reused")
        self.assertEqual(len(calls), 4)

    async def test_operation_failure_is_redacted_by_collector(self):
        private_text = "private-operation-detail"
        calls = []

        async def deployment(**_scope):
            calls.append("deployment")
            raise RuntimeError(private_text)

        async def unreachable(**_scope):
            calls.append("unreachable")
            raise AssertionError("must not run")

        instance = R1ActivationDormantRealBinding(
            operations=R1ActivationRealOperations(
                deployment=deployment,
                protected_source=unreachable,
                switches=unreachable,
                participants=unreachable,
            )
        )
        collector = instance.build_after_gate_once(
            _R1ActivationRealBindingPermit()
        )

        result = await collector.collect()

        self.assertEqual(result.reason, "probe_failed")
        self.assertNotIn(private_text, repr(result))
        self.assertEqual(calls, ["deployment"])

    def test_module_has_no_real_execution_surface_or_defaults(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "r1_pre_event_activation_real_binding.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "dotenv",
            "ctypes.",
            "credread",
            "build_real_windows_credential_backend",
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
