import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.r1_pre_event_activation_evidence_collector import (
    R1ActivationEvidenceCollector,
    SanitizedDeploymentEvidence,
    SanitizedParticipantEvidence,
    SanitizedProtectedSourceEvidence,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    BOT_NEXT_ID,
    BOT_NIA_ID,
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


def deployment():
    return SanitizedDeploymentEvidence(
        deployed_sha=DEPLOYED_MERGE_SHA,
        deployed_tree=DEPLOYED_TREE_SHA,
        workflow_success=True,
        dormant_health_verified=True,
        full_tests_passed=True,
    )


def protected():
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


def switches():
    return tuple(
        SanitizedSwitchBaseline(
            name=name,
            present=True,
            value=EXPECTED_BASELINE_VALUES[name],
        )
        for name in SWITCH_ORDER
    )


def participants():
    return SanitizedParticipantEvidence(
        deal_id=CONTROLLED_DEAL_ID,
        chat_id=CONTROLLED_CHAT_ID,
        dialog_id=CONTROLLED_DIALOG_ID,
        bot_nia_absent=True,
        bot_next_absent=True,
    )


class Probe:
    def __init__(self, result, events, name):
        self.result = result
        self.events = events
        self.name = name
        self.calls = []

    async def collect(self, **kwargs):
        self.events.append(self.name)
        self.calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def collector(*, deployment_result=None, protected_result=None,
              switch_result=None, participant_result=None):
    events = []
    probes = (
        Probe(deployment_result or deployment(), events, "deployment"),
        Probe(protected_result or protected(), events, "protected-source"),
        Probe(switch_result or switches(), events, "switches"),
        Probe(participant_result or participants(), events, "participants"),
    )
    instance = R1ActivationEvidenceCollector(
        deployment_probe=probes[0],
        protected_probe=probes[1],
        switch_probe=probes[2],
        participant_probe=probes[3],
    )
    return instance, probes, events


class R1ActivationEvidenceCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_evidence_is_collected_once_but_never_authorizes(self):
        instance, probes, events = collector()

        result = await instance.collect()

        self.assertEqual(result.state, "EVIDENCE-COLLECTED")
        self.assertEqual(result.reason, "exact_sanitized_evidence")
        self.assertEqual(result.preflight.state, "READY-FIRST-CONFIRMATION")
        self.assertFalse(result.activation_authorized)
        self.assertFalse(result.preflight.activation_authorized)
        self.assertEqual(result.collector_mutations, 0)
        self.assertEqual(events, ["deployment", "protected-source", "switches", "participants"])
        self.assertTrue(all(len(probe.calls) == 1 for probe in probes))

    async def test_probes_receive_only_exact_allowlisted_scope(self):
        instance, probes, _events = collector()
        await instance.collect()

        self.assertEqual(
            probes[0].calls,
            [{"expected_sha": DEPLOYED_MERGE_SHA, "expected_tree": DEPLOYED_TREE_SHA}],
        )
        self.assertEqual(
            probes[1].calls,
            [{"target_id": PROTECTED_TARGET_ID, "expected_setting_count": 7}],
        )
        self.assertEqual(probes[2].calls, [{"names": SWITCH_ORDER}])
        self.assertEqual(
            probes[3].calls,
            [{
                "deal_id": CONTROLLED_DEAL_ID,
                "chat_id": CONTROLLED_CHAT_ID,
                "dialog_id": CONTROLLED_DIALOG_ID,
                "bot_ids": (BOT_NIA_ID, BOT_NEXT_ID),
            }],
        )

    async def test_reuse_is_no_go_without_repeating_any_probe(self):
        instance, probes, _events = collector()
        await instance.collect()

        repeated = await instance.collect()

        self.assertEqual((repeated.state, repeated.reason), ("NO-GO", "collector_reused"))
        self.assertTrue(all(len(probe.calls) == 1 for probe in probes))

    async def test_deployment_drift_stops_before_protected_source(self):
        instance, probes, events = collector(
            deployment_result=replace(deployment(), workflow_success=False)
        )

        result = await instance.collect()

        self.assertEqual(result.reason, "deployment_evidence_invalid")
        self.assertEqual(events, ["deployment"])
        self.assertTrue(all(not probe.calls for probe in probes[1:]))

    async def test_protected_drift_stops_before_switches(self):
        instance, probes, events = collector(
            protected_result=replace(protected(), secret_values_exposed=True)
        )

        result = await instance.collect()

        self.assertEqual(result.reason, "protected_evidence_invalid")
        self.assertEqual(events, ["deployment", "protected-source"])
        self.assertTrue(all(not probe.calls for probe in probes[2:]))

    async def test_switch_drift_stops_before_participant_probe(self):
        drifted = (*switches()[:2], replace(switches()[2], value="pre-event"))
        instance, probes, events = collector(switch_result=drifted)

        result = await instance.collect()

        self.assertEqual(result.reason, "switch_evidence_invalid")
        self.assertEqual(events, ["deployment", "protected-source", "switches"])
        self.assertFalse(probes[3].calls)

    async def test_probe_exception_is_redacted_and_never_retried(self):
        private_text = "private-value-must-not-escape"
        instance, probes, events = collector(
            protected_result=RuntimeError(private_text)
        )

        result = await instance.collect()

        self.assertEqual(result.reason, "probe_failed")
        self.assertNotIn(private_text, repr(result))
        self.assertEqual(events, ["deployment", "protected-source"])
        self.assertEqual(len(probes[1].calls), 1)

    def test_module_has_no_real_binding_or_private_source_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "r1_pre_event_activation_evidence_collector.py"
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
