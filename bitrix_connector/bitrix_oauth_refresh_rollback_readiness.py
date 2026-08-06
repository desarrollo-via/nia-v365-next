"""Auditoría hermética del rollback exigido para renovar OAuth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OAuthRefreshRollbackEvidence:
    refresh_rotates_external_pair: bool
    conditional_persistence: bool
    persistence_readback: bool
    provider_rollback_endpoint_available: bool
    previous_pair_valid_after_rotation: bool


@dataclass(frozen=True)
class OAuthRefreshRollbackReadiness:
    phase: Literal["M86-CB"] = "M86-CB"
    state: Literal[
        "READY-TO-PREPARE-FIRST-CONFIRMATION",
        "DO-NOT-REQUEST",
    ] = "DO-NOT-REQUEST"
    conditional_persistence_verified: bool = False
    persistence_readback_verified: bool = False
    exact_rollback_available: bool = False
    local_restore_safe: bool = False
    two_confirmations_required: Literal[True] = True
    first_confirmation_ready: bool = False
    second_confirmation_ready: Literal[False] = False
    external_calls: Literal[0] = 0
    source_open_calls: Literal[0] = 0
    oauth_refresh_calls: Literal[0] = 0
    mongo_read_calls: Literal[0] = 0
    mongo_write_calls: Literal[0] = 0
    bitrix_calls: Literal[0] = 0


def audit_oauth_refresh_rollback_readiness(
    evidence: OAuthRefreshRollbackEvidence,
) -> OAuthRefreshRollbackReadiness:
    if type(evidence) is not OAuthRefreshRollbackEvidence:
        return OAuthRefreshRollbackReadiness()
    exact = bool(
        evidence.refresh_rotates_external_pair
        and evidence.provider_rollback_endpoint_available
        and evidence.previous_pair_valid_after_rotation
    )
    safe_restore = bool(exact and evidence.conditional_persistence)
    ready = bool(
        evidence.conditional_persistence
        and evidence.persistence_readback
        and safe_restore
    )
    return OAuthRefreshRollbackReadiness(
        state=(
            "READY-TO-PREPARE-FIRST-CONFIRMATION"
            if ready
            else "DO-NOT-REQUEST"
        ),
        conditional_persistence_verified=evidence.conditional_persistence,
        persistence_readback_verified=evidence.persistence_readback,
        exact_rollback_available=exact,
        local_restore_safe=safe_restore,
        first_confirmation_ready=ready,
    )


def audit_current_oauth_refresh_owner() -> OAuthRefreshRollbackReadiness:
    """Refleja el contrato actual sin construir fuentes o recursos reales."""

    return audit_oauth_refresh_rollback_readiness(
        OAuthRefreshRollbackEvidence(
            refresh_rotates_external_pair=True,
            conditional_persistence=True,
            persistence_readback=True,
            provider_rollback_endpoint_available=False,
            previous_pair_valid_after_rotation=False,
        )
    )


__all__ = [
    "OAuthRefreshRollbackEvidence",
    "OAuthRefreshRollbackReadiness",
    "audit_current_oauth_refresh_owner",
    "audit_oauth_refresh_rollback_readiness",
]
