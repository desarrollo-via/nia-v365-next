"""Mapa M86-AK de rutas NO-GO, sin ejecutar fuentes ni revelar claves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PublicFailureCategory = Literal[
    "authorization_invalid",
    "source_aggregate_unavailable",
    "candidate_not_fit",
    "composition_failed",
    "cleanup_ambiguous",
]


@dataclass(frozen=True)
class M86AKNoGoRoute:
    internal_stage: Literal[
        "authorization_gate",
        "source_factory",
        "source_open",
        "source_transfer",
        "candidate_materialization",
        "candidate_fit_check",
        "unexpected_composition",
        "terminal_cleanup",
    ]
    public_category: PublicFailureCategory
    reveals_individual_key: Literal[False] = False
    reveals_value: Literal[False] = False
    reveals_length: Literal[False] = False
    reveals_progress_count: Literal[False] = False


M86AK_NO_GO_ROUTES = (
    M86AKNoGoRoute("authorization_gate", "authorization_invalid"),
    M86AKNoGoRoute("source_factory", "source_aggregate_unavailable"),
    M86AKNoGoRoute("source_open", "source_aggregate_unavailable"),
    M86AKNoGoRoute("source_transfer", "source_aggregate_unavailable"),
    M86AKNoGoRoute("candidate_materialization", "candidate_not_fit"),
    M86AKNoGoRoute("candidate_fit_check", "candidate_not_fit"),
    M86AKNoGoRoute("unexpected_composition", "composition_failed"),
    M86AKNoGoRoute("terminal_cleanup", "cleanup_ambiguous"),
)


@dataclass(frozen=True)
class M86AKRouteAudit:
    phase: Literal["M86-AK"] = "M86-AK"
    state: Literal["MAPPED-INERT"] = "MAPPED-INERT"
    routes: tuple[M86AKNoGoRoute, ...] = M86AK_NO_GO_ROUTES
    current_real_read_budget: Literal[0] = 0
    real_probe_authorized: Literal[False] = False
    real_probe_executed: Literal[False] = False
    external_calls: Literal[0] = 0

    def __post_init__(self) -> None:
        stages = tuple(route.internal_stage for route in self.routes)
        if len(stages) != len(set(stages)) or len(stages) != 8:
            raise ValueError("m86ak_route_map_invalid")


__all__ = [
    "M86AKNoGoRoute",
    "M86AKRouteAudit",
    "M86AK_NO_GO_ROUTES",
    "PublicFailureCategory",
]
