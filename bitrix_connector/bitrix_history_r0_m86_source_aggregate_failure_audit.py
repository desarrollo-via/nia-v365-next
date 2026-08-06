"""Auditoría M86-AR del NO-GO agregado, sin abrir fuentes reales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_no_go_route_audit import M86AK_NO_GO_ROUTES


SOURCE_AGGREGATE_STAGES = (
    "source_factory",
    "source_open",
    "source_transfer",
)


@dataclass(frozen=True)
class M86ARSourceAggregateFailureAudit:
    phase: Literal["M86-AR"] = "M86-AR"
    state: Literal["SOURCE-STAGES-AUDITED"] = "SOURCE-STAGES-AUDITED"
    observed_public_result: Literal[
        "NO-GO/source_aggregate_unavailable"
    ] = "NO-GO/source_aggregate_unavailable"
    possible_internal_stages: tuple[
        Literal["source_factory", "source_open", "source_transfer"], ...
    ] = SOURCE_AGGREGATE_STAGES
    exact_internal_stage_identified: Literal[False] = False
    individual_key_identified: Literal[False] = False
    value_disclosed: Literal[False] = False
    new_real_read_budget: Literal[0] = 0
    real_probe_retried: Literal[False] = False
    external_calls: Literal[0] = 0

    def __post_init__(self) -> None:
        mapped = tuple(
            route.internal_stage
            for route in M86AK_NO_GO_ROUTES
            if route.public_category == "source_aggregate_unavailable"
        )
        if mapped != self.possible_internal_stages:
            raise ValueError("m86ar_source_stage_map_invalid")


__all__ = [
    "M86ARSourceAggregateFailureAudit",
    "SOURCE_AGGREGATE_STAGES",
]
