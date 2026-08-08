"""Readiness M86-AS sin ejecutar el factory fixture ni enlazar fuente real."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_stage_specific_fixture_owner import (
    M86ASStageSpecificFixtureOwner,
)
from .bitrix_history_r0_m86_stage_specific_source_diagnostic import (
    M86AS_SOURCE_FAILURE_CATEGORIES,
)


@dataclass(frozen=True)
class M86ASReadinessSnapshot:
    phase: Literal["M86-AS"] = "M86-AS"
    state: Literal["READY-HERMETIC", "NO-GO"] = "NO-GO"
    categories_frozen: bool = False
    fixture_owner_dormant: bool = False
    fixture_factory_calls: Literal[0] = 0
    real_source_bound: Literal[False] = False
    real_read_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86as_readiness(*, owner: M86ASStageSpecificFixtureOwner) -> M86ASReadinessSnapshot:
    if type(owner) is not M86ASStageSpecificFixtureOwner:
        return M86ASReadinessSnapshot()
    preview = owner.preview()
    categories_frozen = M86AS_SOURCE_FAILURE_CATEGORIES == (
        "source_factory_unavailable",
        "source_open_unavailable",
        "source_transfer_unavailable",
    )
    ready = (
        categories_frozen
        and preview.state == "FIXTURE-DORMANT"
        and not preview.fixture_factory_called
        and not preview.real_source_bound
        and preview.real_read_budget == 0
    )
    return M86ASReadinessSnapshot(
        state="READY-HERMETIC" if ready else "NO-GO",
        categories_frozen=categories_frozen,
        fixture_owner_dormant=True,
    )


__all__ = ["M86ASReadinessSnapshot", "audit_m86as_readiness"]
