"""Readiness M86-AT sin invocar fábrica ni preparar autorización real."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_stage_specific_dormant_real_owner import (
    M86ATStageSpecificDormantRealOwner,
)
from .bitrix_history_r0_m86_stage_specific_source_diagnostic import (
    M86AS_SOURCE_FAILURE_CATEGORIES,
)


@dataclass(frozen=True)
class M86ATReadinessSnapshot:
    phase: Literal["M86-AT"] = "M86-AT"
    state: Literal["READY-TO-DESIGN-AUTHORIZATION", "NO-GO"] = "NO-GO"
    categories_reused: bool = False
    owner_dormant: bool = False
    real_factory_bound: bool = False
    real_factory_calls: Literal[0] = 0
    authorization_literal_prepared: Literal[False] = False
    authorization_received: Literal[False] = False
    execution_surface_available: Literal[False] = False
    execution_surface_has_cli: Literal[False] = False
    real_read_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86at_readiness(
    *, owner: M86ATStageSpecificDormantRealOwner,
) -> M86ATReadinessSnapshot:
    if type(owner) is not M86ATStageSpecificDormantRealOwner:
        return M86ATReadinessSnapshot()
    preview = owner.preview()
    categories_reused = M86AS_SOURCE_FAILURE_CATEGORIES == (
        "source_factory_unavailable",
        "source_open_unavailable",
        "source_transfer_unavailable",
    )
    ready = (
        categories_reused
        and preview.state == "DORMANT-WAITING-AUTHORIZATION-DESIGN"
        and preview.real_factory_bound
        and not preview.real_factory_called
        and not preview.authorization_literal_prepared
        and not preview.authorization_received
        and not preview.execution_surface_available
        and not preview.execution_surface_has_cli
        and preview.current_real_read_budget == 0
    )
    return M86ATReadinessSnapshot(
        state="READY-TO-DESIGN-AUTHORIZATION" if ready else "NO-GO",
        categories_reused=categories_reused,
        owner_dormant=True,
        real_factory_bound=preview.real_factory_bound,
    )


__all__ = ["M86ATReadinessSnapshot", "audit_m86at_readiness"]
