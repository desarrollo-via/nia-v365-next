"""Readiness M86-AU sin mostrar el literal ni enlazar ejecución."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_stage_specific_dormant_real_owner import (
    M86ATStageSpecificDormantRealOwner,
)
from .bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AU_PUBLIC_CATEGORIES,
    M86AUAuthorizationContract,
)


@dataclass(frozen=True)
class M86AUReadinessSnapshot:
    phase: Literal["M86-AU"] = "M86-AU"
    state: Literal["READY-TO-SHOW-STAGE-AUTHORIZATION", "NO-GO"] = "NO-GO"
    categories_frozen: bool = False
    owner_dormant: bool = False
    real_factory_bound: bool = False
    real_factory_calls: Literal[0] = 0
    literal_prepared: bool = False
    literal_shown: Literal[False] = False
    authorization_received: Literal[False] = False
    linked_to_execution: Literal[False] = False
    execution_surface_available: Literal[False] = False
    real_read_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86au_readiness(
    *,
    owner: M86ATStageSpecificDormantRealOwner,
    authorization: M86AUAuthorizationContract,
) -> M86AUReadinessSnapshot:
    if type(owner) is not M86ATStageSpecificDormantRealOwner:
        return M86AUReadinessSnapshot()
    preview = owner.preview()
    if type(authorization) is not M86AUAuthorizationContract:
        return M86AUReadinessSnapshot(
            owner_dormant=True,
            real_factory_bound=preview.real_factory_bound,
        )
    categories_frozen = M86AU_PUBLIC_CATEGORIES == (
        "authorization_invalid",
        "source_factory_unavailable",
        "source_open_unavailable",
        "source_transfer_unavailable",
        "candidate_not_fit",
        "composition_failed",
        "cleanup_ambiguous",
    )
    ready = (
        categories_frozen
        and preview.state == "DORMANT-WAITING-AUTHORIZATION-DESIGN"
        and preview.real_factory_bound
        and not preview.real_factory_called
        and not preview.execution_surface_available
        and authorization.state == "PREPARED-NOT-SHOWN"
        and not authorization.shown_to_person
        and not authorization.authorization_received
        and not authorization.linked_to_execution
        and authorization.current_real_read_budget == 0
    )
    return M86AUReadinessSnapshot(
        state="READY-TO-SHOW-STAGE-AUTHORIZATION" if ready else "NO-GO",
        categories_frozen=categories_frozen,
        owner_dormant=True,
        real_factory_bound=preview.real_factory_bound,
        literal_prepared=True,
    )


__all__ = ["M86AUReadinessSnapshot", "audit_m86au_readiness"]
