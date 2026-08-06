"""Readiness M86-AV sin mostrar literal ni invocar la fábrica real."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AUAuthorizationContract,
)
from .bitrix_history_r0_m86_stage_specific_real_owner import (
    M86AVStageSpecificRealOwner,
)


@dataclass(frozen=True)
class M86AVReadinessSnapshot:
    phase: Literal["M86-AV"] = "M86-AV"
    state: Literal["READY-TO-SHOW-STAGE-AUTHORIZATION", "NO-GO"] = "NO-GO"
    owner_dormant: bool = False
    one_shot_execution_bound: bool = False
    real_factory_bound: bool = False
    real_factory_calls: Literal[0] = 0
    literal_prepared: bool = False
    literal_shown: Literal[False] = False
    authorization_received: Literal[False] = False
    execution_surface_has_cli: Literal[False] = False
    real_read_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86av_readiness(
    *, owner: M86AVStageSpecificRealOwner,
    authorization: M86AUAuthorizationContract,
) -> M86AVReadinessSnapshot:
    if type(owner) is not M86AVStageSpecificRealOwner:
        return M86AVReadinessSnapshot()
    preview = owner.preview()
    if type(authorization) is not M86AUAuthorizationContract:
        return M86AVReadinessSnapshot(
            owner_dormant=True,
            real_factory_bound=preview.real_factory_bound,
        )
    ready = (
        preview.state == "DORMANT-WAITING-EXACT-AUTHORIZATION"
        and preview.real_factory_bound
        and not preview.real_factory_called
        and preview.execution_surface_one_shot
        and not preview.execution_surface_has_cli
        and not preview.authorization_received
        and preview.current_real_read_budget == 0
        and authorization.state == "PREPARED-NOT-SHOWN"
        and not authorization.shown_to_person
        and not authorization.authorization_received
    )
    return M86AVReadinessSnapshot(
        state="READY-TO-SHOW-STAGE-AUTHORIZATION" if ready else "NO-GO",
        owner_dormant=True,
        one_shot_execution_bound=preview.execution_surface_one_shot,
        real_factory_bound=preview.real_factory_bound,
        literal_prepared=True,
    )


__all__ = ["M86AVReadinessSnapshot", "audit_m86av_readiness"]
