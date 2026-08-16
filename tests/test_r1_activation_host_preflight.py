import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from bitrix_connector.controlled_chat_participant_adapter import ChatParticipantSnapshot
from bitrix_connector.controlled_chat_participant_http import (
    ParticipantHttpDecision,
    ParticipantReadResult,
)
from bitrix_connector.r1_activation_host_preflight import (
    ExactR1ActivationHostPreflight,
    R1ActivationHostPreflightFailure,
    read_packaged_deployment_identity,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA, PROTECTED_TARGET_ID,
    audit_r1_activation_preflight,
)


PROTECTED_VALUES = {
    "NIA_BITRIX_DOMAIN": "viaindustrial.bitrix24.es",
    "NIA_BITRIX_MEMBER_ID": "member-fixture",
    "NIA_BITRIX_CLIENT_ID": "client-fixture",
    "NIA_BITRIX_CLIENT_SECRET": "secret-fixture",
    "NIA_BITRIX_MONGO_URI": "mongodb://fixture.invalid/nia",
    "NIA_BITRIX_MONGO_DB": "nia",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "installations",
}


class Backend:
    def __init__(self):
        self.fetches = 0
        self.closed = False

    async def fetch_exact(self, target_id):
        self.fetches += 1
        return InjectedWindowsCredentialRecord(
            target_id=target_id,
            buffers={
                name: bytearray(PROTECTED_VALUES[name].encode())
                for name in PROTECTED_SETTING_NAMES
            },
        )

    async def close(self):
        self.closed = True


class Provider:
    def __init__(self): self.calls = 0
    async def get_access_token(self, member_id):
        self.calls += 1
        return "oauth-token-fixture"


class OAuthResources:
    def __init__(self):
        self.oauth_provider = Provider()
        self.portal_url = "https://viaindustrial.bitrix24.es"
        self.member_id = "member-fixture"
        self.closed = False

    async def close(self): self.closed = True


class OAuthFactory:
    def __init__(self, resources): self.resources = resources; self.calls = 0
    async def build(self, settings, *, timeout_seconds):
        self.calls += 1
        return self.resources


class Reader:
    async def read(self):
        return ParticipantReadResult(
            decision=ParticipantHttpDecision.SUCCESS,
            snapshot=ChatParticipantSnapshot(
                crm_entity_id=614949,
                chat_id=78733,
                dialog_id="chat78733",
                participant_ids=frozenset({99}),
            ),
            http_status=200,
            pages=1,
        )


class ParticipantResources:
    def __init__(self): self.reader = Reader(); self.closed = False
    async def close(self): self.closed = True


class R1ActivationHostPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_recoverable_protected_source_does_not_consume_collector(self):
        class FailingBackend(Backend):
            async def fetch_exact(self, _target_id):
                self.fetches += 1
                raise RuntimeError("fixture-unavailable")

        builds = []
        oauth = OAuthResources()
        participant = ParticipantResources()

        def backend_builder(**_kwargs):
            backend = FailingBackend() if not builds else Backend()
            builds.append(backend)
            return backend

        probe = ExactR1ActivationHostPreflight(
            environ={
                "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-123456789",
                "NIA_BITRIX_KEY_VAULT_URL": "https://fixture.vault.azure.net",
                "NIA_BITRIX_R0_BRIDGE_ENABLED": "false",
                "NIA_BITRIX_EVENT_R1_ENABLED": "false",
                "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY": "posterior",
            },
            backend_builder=backend_builder,
            oauth_factory_builder=lambda: OAuthFactory(oauth),
            http_resources_factory=lambda **_kwargs: participant,
            deployment_identity_supplier=lambda: (
                DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA
            ),
        )
        with self.assertRaises(R1ActivationHostPreflightFailure) as captured:
            await probe.collect_once()
        self.assertEqual(captured.exception.stage, "protected_source")
        self.assertEqual(
            captured.exception.category, "protected_source_unavailable"
        )
        self.assertTrue(captured.exception.retryable)
        self.assertEqual(captured.exception.attempts, 1)
        self.assertTrue(builds[0].closed)
        evidence = await probe.collect_once()
        self.assertEqual(evidence.chat_id, 78733)
        self.assertEqual(len(builds), 2)

    async def test_packaged_identity_is_exact_and_rejects_drift(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            path.write_text(json.dumps({
                "commit": "a" * 40, "tree": "b" * 40
            }), encoding="utf-8")
            with patch(
                "bitrix_connector.r1_activation_host_preflight.DEPLOYMENT_IDENTITY_PATH",
                path,
            ):
                self.assertEqual(
                    read_packaged_deployment_identity(), ("a" * 40, "b" * 40)
                )
                path.write_text(json.dumps({"commit": "a" * 40}), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "identity_invalid"):
                    read_packaged_deployment_identity()

    async def test_collects_exact_ready_evidence_and_closes_every_resource(self):
        environ = {
            "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-123456789",
            "NIA_BITRIX_KEY_VAULT_URL": "https://fixture.vault.azure.net",
            "NIA_BITRIX_R0_BRIDGE_ENABLED": "false",
            "NIA_BITRIX_EVENT_R1_ENABLED": "false",
            "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY": "posterior",
        }
        backend = Backend()
        oauth = OAuthResources()
        oauth_factory = OAuthFactory(oauth)
        participant = ParticipantResources()
        probe = ExactR1ActivationHostPreflight(
            environ=environ,
            backend_builder=lambda **_kwargs: backend,
            oauth_factory_builder=lambda: oauth_factory,
            http_resources_factory=lambda **_kwargs: participant,
            deployment_identity_supplier=lambda: (
                DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA
            ),
        )
        evidence = await probe.collect_once()
        result = audit_r1_activation_preflight(evidence)
        self.assertEqual(result.state, "READY-FIRST-CONFIRMATION")
        self.assertTrue(result.protected_source_verified)
        self.assertTrue(result.participant_baseline_verified)
        self.assertEqual(backend.fetches, 1)
        self.assertEqual(oauth.oauth_provider.calls, 1)
        self.assertTrue(backend.closed)
        self.assertTrue(oauth.closed)
        self.assertTrue(participant.closed)
        self.assertEqual(repr(probe), "ExactR1ActivationHostPreflight(<redacted>)")
        with self.assertRaisesRegex(RuntimeError, "reused"):
            await probe.collect_once()

    async def test_bot_next_present_fails_closed_without_mutation(self):
        class PresentReader:
            async def read(self):
                return ParticipantReadResult(
                    decision=ParticipantHttpDecision.SUCCESS,
                    snapshot=ChatParticipantSnapshot(
                        crm_entity_id=614949, chat_id=78733,
                        dialog_id="chat78733", participant_ids=frozenset({373259}),
                    ),
                    http_status=200, pages=1,
                )

        participant = ParticipantResources()
        participant.reader = PresentReader()
        oauth = OAuthResources()
        probe = ExactR1ActivationHostPreflight(
            environ={
                "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-123456789",
                "NIA_BITRIX_KEY_VAULT_URL": "https://fixture.vault.azure.net",
                "NIA_BITRIX_R0_BRIDGE_ENABLED": "false",
                "NIA_BITRIX_EVENT_R1_ENABLED": "false",
                "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY": "posterior",
            },
            backend_builder=lambda **_kwargs: Backend(),
            oauth_factory_builder=lambda: OAuthFactory(oauth),
            http_resources_factory=lambda **_kwargs: participant,
            deployment_identity_supplier=lambda: (
                DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA
            ),
        )
        evidence = await probe.collect_once()
        self.assertEqual(audit_r1_activation_preflight(evidence).state, "NO-GO")
        self.assertTrue(oauth.closed)
        self.assertTrue(participant.closed)

    async def test_baseline_failures_preserve_exact_nonsecret_category(self):
        baseline = {
            "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-123456789",
            "NIA_BITRIX_KEY_VAULT_URL": "https://fixture.vault.azure.net",
            "NIA_BITRIX_R0_BRIDGE_ENABLED": "false",
            "NIA_BITRIX_EVENT_R1_ENABLED": "false",
            "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY": "posterior",
        }
        cases = (
            ("NIA_BITRIX_REVIEW_TOKEN", None, "baseline_review_token_missing"),
            ("NIA_BITRIX_KEY_VAULT_URL", None, "baseline_key_vault_url_missing"),
            ("NIA_BITRIX_R0_BRIDGE_ENABLED", "true", "baseline_r0_bridge_enabled"),
            ("NIA_BITRIX_EVENT_R1_ENABLED", "true", "baseline_event_r1_enabled"),
            (
                "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY", "pre-event",
                "baseline_participant_strategy_drift",
            ),
        )
        for name, value, expected in cases:
            with self.subTest(category=expected):
                environ = dict(baseline)
                if value is None:
                    environ.pop(name)
                else:
                    environ[name] = value
                probe = ExactR1ActivationHostPreflight(
                    environ=environ,
                    backend_builder=lambda **_kwargs: None,
                    oauth_factory_builder=lambda: None,
                    http_resources_factory=lambda **_kwargs: None,
                    deployment_identity_supplier=lambda: (
                        DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA
                    ),
                )
                with self.assertRaises(R1ActivationHostPreflightFailure) as raised:
                    await probe.collect_once()
                self.assertEqual(raised.exception.stage, "baseline")
                self.assertEqual(raised.exception.category, expected)
                self.assertFalse(raised.exception.retryable)

    async def test_participant_failure_preserves_reader_category(self):
        class FailedReader:
            async def read(self):
                return ParticipantReadResult(
                    decision=ParticipantHttpDecision.FAIL,
                    error_code="participant_list_rejected", http_status=403,
                    pages=1,
                )
        participant = ParticipantResources()
        participant.reader = FailedReader()
        probe = ExactR1ActivationHostPreflight(
            environ={
                "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-123456789",
                "NIA_BITRIX_KEY_VAULT_URL": "https://fixture.vault.azure.net",
                "NIA_BITRIX_R0_BRIDGE_ENABLED": "false",
                "NIA_BITRIX_EVENT_R1_ENABLED": "false",
                "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY": "posterior",
            },
            backend_builder=lambda **_kwargs: Backend(),
            oauth_factory_builder=lambda: OAuthFactory(OAuthResources()),
            http_resources_factory=lambda **_kwargs: participant,
            deployment_identity_supplier=lambda: (DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA),
        )
        with self.assertRaises(R1ActivationHostPreflightFailure) as raised:
            await probe.collect_once()
        self.assertEqual(raised.exception.stage, "participants")
        self.assertEqual(raised.exception.category, "participant_list_rejected")
        self.assertTrue(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
