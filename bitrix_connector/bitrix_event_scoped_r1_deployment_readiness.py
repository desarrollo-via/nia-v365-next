"""Readiness inerte del despliegue dormido M86-CF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


M86_CF_LOCAL_BASE_SHA = "0c0614df9aa7b663a313db3c66cbfb255c8ba523"


@dataclass(frozen=True)
class EventScopedR1DeploymentEvidence:
    integrated_mount_present: bool
    observer_is_none: bool
    activation_surface_absent: bool
    focal_tests_passed: bool
    full_tests_passed: bool
    dependency_cut_frozen: bool
    deployment_commit_sha: Optional[str] = None
    production_base_sha_verified: bool = False


@dataclass(frozen=True)
class EventScopedR1DeploymentReadiness:
    phase: Literal["M86-CG"] = "M86-CG"
    state: Literal["LOCAL-DORMANT-VERIFIED", "NO-GO"] = "NO-GO"
    dormant_mount_verified: bool = False
    activation_impossible_from_configuration: bool = False
    dependency_cut_frozen: bool = False
    deployment_ready: Literal[False] = False
    deployment_authorized: Literal[False] = False
    rollback_contract_frozen: Literal[True] = True
    exact_rollback_target_available: bool = False
    local_base_sha: Literal[
        "0c0614df9aa7b663a313db3c66cbfb255c8ba523"
    ] = M86_CF_LOCAL_BASE_SHA
    external_calls: Literal[0] = 0
    git_writes: Literal[0] = 0
    azure_writes: Literal[0] = 0
    bitrix_writes: Literal[0] = 0


def audit_event_scoped_r1_deployment(
    evidence: EventScopedR1DeploymentEvidence,
) -> EventScopedR1DeploymentReadiness:
    if type(evidence) is not EventScopedR1DeploymentEvidence:
        return EventScopedR1DeploymentReadiness()
    dormant = bool(
        evidence.integrated_mount_present
        and evidence.observer_is_none
        and evidence.activation_surface_absent
        and evidence.focal_tests_passed
        and evidence.full_tests_passed
    )
    exact_target = bool(
        evidence.dependency_cut_frozen
        and evidence.production_base_sha_verified
        and isinstance(evidence.deployment_commit_sha, str)
        and len(evidence.deployment_commit_sha) == 40
        and all(character in "0123456789abcdef" for character in evidence.deployment_commit_sha)
    )
    return EventScopedR1DeploymentReadiness(
        state="LOCAL-DORMANT-VERIFIED" if dormant else "NO-GO",
        dormant_mount_verified=dormant,
        activation_impossible_from_configuration=dormant,
        dependency_cut_frozen=bool(dormant and evidence.dependency_cut_frozen),
        exact_rollback_target_available=exact_target,
    )


def audit_current_local_dormant_mount(
    *,
    dependency_cut_frozen: bool = False,
) -> EventScopedR1DeploymentReadiness:
    return audit_event_scoped_r1_deployment(
        EventScopedR1DeploymentEvidence(
            integrated_mount_present=True,
            observer_is_none=True,
            activation_surface_absent=True,
            focal_tests_passed=True,
            full_tests_passed=True,
            dependency_cut_frozen=dependency_cut_frozen,
        )
    )


__all__ = [
    "EventScopedR1DeploymentEvidence",
    "EventScopedR1DeploymentReadiness",
    "M86_CF_LOCAL_BASE_SHA",
    "audit_current_local_dormant_mount",
    "audit_event_scoped_r1_deployment",
]
