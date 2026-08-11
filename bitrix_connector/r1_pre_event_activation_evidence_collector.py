"""One-shot collector for sanitized R1 activation evidence.

This module only coordinates explicitly injected probes.  It has no real
backend, environment, network, credential, OAuth, Bitrix, or Azure binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from .r1_pre_event_activation_preflight import (
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
    R1ActivationPreflight,
    R1ActivationPreflightEvidence,
    SanitizedSwitchBaseline,
    audit_r1_activation_preflight,
)


@dataclass(frozen=True)
class SanitizedDeploymentEvidence:
    deployed_sha: str
    deployed_tree: str
    workflow_success: bool
    dormant_health_verified: bool
    full_tests_passed: bool


@dataclass(frozen=True)
class SanitizedProtectedSourceEvidence:
    host_supports_protected_source: bool
    protected_source_kind: str
    protected_target_id: str
    protected_record_shape_verified: bool
    protected_setting_count: int
    credential_read_calls: int
    oauth_read_calls: int
    refresh_calls: int
    retry_calls: int
    resources_closed: bool
    review_auth_configured: bool
    secret_values_exposed: bool = False


@dataclass(frozen=True)
class SanitizedParticipantEvidence:
    deal_id: int
    chat_id: int
    dialog_id: str
    bot_nia_absent: bool
    bot_next_absent: bool


class DeploymentEvidenceProbe(Protocol):
    async def collect(
        self, *, expected_sha: str, expected_tree: str
    ) -> SanitizedDeploymentEvidence: ...


class ProtectedSourceEvidenceProbe(Protocol):
    async def collect(
        self, *, target_id: str, expected_setting_count: int
    ) -> SanitizedProtectedSourceEvidence: ...


class SwitchBaselineProbe(Protocol):
    async def collect(
        self, *, names: tuple[str, ...]
    ) -> tuple[SanitizedSwitchBaseline, ...]: ...


class ParticipantBaselineProbe(Protocol):
    async def collect(
        self,
        *,
        deal_id: int,
        chat_id: int,
        dialog_id: str,
        bot_ids: tuple[int, int],
    ) -> SanitizedParticipantEvidence: ...


@dataclass(frozen=True)
class R1ActivationEvidenceCollection:
    state: Literal["EVIDENCE-COLLECTED", "NO-GO"] = "NO-GO"
    reason: str = "collector_not_run"
    evidence: Optional[R1ActivationPreflightEvidence] = None
    preflight: R1ActivationPreflight = R1ActivationPreflight()
    probe_calls: tuple[str, ...] = ()
    collector_mutations: Literal[0] = 0
    activation_authorized: Literal[False] = False


def _deployment_ready(item: object) -> bool:
    return bool(
        type(item) is SanitizedDeploymentEvidence
        and item.deployed_sha == DEPLOYED_MERGE_SHA
        and item.deployed_tree == DEPLOYED_TREE_SHA
        and item.workflow_success
        and item.dormant_health_verified
        and item.full_tests_passed
    )


def _protected_ready(item: object) -> bool:
    return bool(
        type(item) is SanitizedProtectedSourceEvidence
        and item.host_supports_protected_source
        and item.protected_source_kind == PROTECTED_SOURCE_KIND
        and item.protected_target_id == PROTECTED_TARGET_ID
        and item.protected_record_shape_verified
        and item.protected_setting_count == PROTECTED_SETTING_COUNT
        and item.credential_read_calls == 1
        and item.oauth_read_calls == 1
        and item.refresh_calls == 0
        and item.retry_calls == 0
        and item.resources_closed
        and item.review_auth_configured
        and not item.secret_values_exposed
    )


def _switches_ready(items: object) -> bool:
    if type(items) is not tuple or len(items) != len(SWITCH_ORDER):
        return False
    for name, item in zip(SWITCH_ORDER, items, strict=True):
        if type(item) is not SanitizedSwitchBaseline or item.name != name:
            return False
        if item.present:
            if item.value != EXPECTED_BASELINE_VALUES[name]:
                return False
        elif item.value is not None:
            return False
    return True


def _participants_ready(item: object) -> bool:
    return bool(
        type(item) is SanitizedParticipantEvidence
        and item.deal_id == CONTROLLED_DEAL_ID
        and item.chat_id == CONTROLLED_CHAT_ID
        and item.dialog_id == CONTROLLED_DIALOG_ID
        and item.bot_nia_absent
        and item.bot_next_absent
    )


class R1ActivationEvidenceCollector:
    """Consumes each injected probe at most once and never retries."""

    __slots__ = (
        "_deployment_probe",
        "_participant_probe",
        "_protected_probe",
        "_switch_probe",
        "_used",
    )

    def __init__(
        self,
        *,
        deployment_probe: DeploymentEvidenceProbe,
        protected_probe: ProtectedSourceEvidenceProbe,
        switch_probe: SwitchBaselineProbe,
        participant_probe: ParticipantBaselineProbe,
    ) -> None:
        probes = (
            deployment_probe,
            protected_probe,
            switch_probe,
            participant_probe,
        )
        if any(not callable(getattr(probe, "collect", None)) for probe in probes):
            raise TypeError("r1_activation_evidence_probe_invalid")
        self._deployment_probe = deployment_probe
        self._protected_probe = protected_probe
        self._switch_probe = switch_probe
        self._participant_probe = participant_probe
        self._used = False

    async def collect(self) -> R1ActivationEvidenceCollection:
        if self._used:
            return R1ActivationEvidenceCollection(reason="collector_reused")
        self._used = True
        calls: list[str] = []

        try:
            calls.append("deployment")
            deployment = await self._deployment_probe.collect(
                expected_sha=DEPLOYED_MERGE_SHA,
                expected_tree=DEPLOYED_TREE_SHA,
            )
            if not _deployment_ready(deployment):
                return self._no_go("deployment_evidence_invalid", calls)

            calls.append("protected-source")
            protected = await self._protected_probe.collect(
                target_id=PROTECTED_TARGET_ID,
                expected_setting_count=PROTECTED_SETTING_COUNT,
            )
            if not _protected_ready(protected):
                return self._no_go("protected_evidence_invalid", calls)

            calls.append("switches")
            switches = await self._switch_probe.collect(names=SWITCH_ORDER)
            if not _switches_ready(switches):
                return self._no_go("switch_evidence_invalid", calls)

            calls.append("participants")
            participants = await self._participant_probe.collect(
                deal_id=CONTROLLED_DEAL_ID,
                chat_id=CONTROLLED_CHAT_ID,
                dialog_id=CONTROLLED_DIALOG_ID,
                bot_ids=(BOT_NIA_ID, BOT_NEXT_ID),
            )
            if not _participants_ready(participants):
                return self._no_go("participant_evidence_invalid", calls)
        except Exception:
            return self._no_go("probe_failed", calls)

        evidence = R1ActivationPreflightEvidence(
            deployed_sha=deployment.deployed_sha,
            deployed_tree=deployment.deployed_tree,
            workflow_success=deployment.workflow_success,
            dormant_health_verified=deployment.dormant_health_verified,
            full_tests_passed=deployment.full_tests_passed,
            host_supports_protected_source=protected.host_supports_protected_source,
            protected_source_kind=protected.protected_source_kind,
            protected_target_id=protected.protected_target_id,
            protected_record_shape_verified=(
                protected.protected_record_shape_verified
            ),
            protected_setting_count=protected.protected_setting_count,
            credential_read_calls=protected.credential_read_calls,
            oauth_read_calls=protected.oauth_read_calls,
            refresh_calls=protected.refresh_calls,
            retry_calls=protected.retry_calls,
            resources_closed=protected.resources_closed,
            review_auth_configured=protected.review_auth_configured,
            switches=switches,
            deal_id=participants.deal_id,
            chat_id=participants.chat_id,
            dialog_id=participants.dialog_id,
            bot_nia_absent=participants.bot_nia_absent,
            bot_next_absent=participants.bot_next_absent,
            secret_values_exposed=protected.secret_values_exposed,
        )
        preflight = audit_r1_activation_preflight(evidence)
        if preflight.state != "READY-FIRST-CONFIRMATION":
            return self._no_go("preflight_rejected", calls)
        return R1ActivationEvidenceCollection(
            state="EVIDENCE-COLLECTED",
            reason="exact_sanitized_evidence",
            evidence=evidence,
            preflight=preflight,
            probe_calls=tuple(calls),
        )

    @staticmethod
    def _no_go(
        reason: str, calls: list[str]
    ) -> R1ActivationEvidenceCollection:
        return R1ActivationEvidenceCollection(
            reason=reason,
            probe_calls=tuple(calls),
        )


__all__ = [
    "DeploymentEvidenceProbe",
    "ParticipantBaselineProbe",
    "ProtectedSourceEvidenceProbe",
    "R1ActivationEvidenceCollection",
    "R1ActivationEvidenceCollector",
    "SanitizedDeploymentEvidence",
    "SanitizedParticipantEvidence",
    "SanitizedProtectedSourceEvidence",
    "SwitchBaselineProbe",
]
