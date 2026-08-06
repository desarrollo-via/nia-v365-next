"""Contrato M86-AL de diagnóstico público agregado y no individual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from .bitrix_history_r0_m86_no_go_route_audit import PublicFailureCategory


PUBLIC_FAILURE_CATEGORIES = (
    "authorization_invalid",
    "source_aggregate_unavailable",
    "candidate_not_fit",
    "composition_failed",
    "cleanup_ambiguous",
)


@dataclass(frozen=True)
class M86ALPublicAggregateDiagnostic:
    phase: Literal["M86-AL"] = "M86-AL"
    state: Literal["FIT", "NO-GO"] = "NO-GO"
    failure_category: Literal[
        "none",
        "authorization_invalid",
        "source_aggregate_unavailable",
        "candidate_not_fit",
        "composition_failed",
        "cleanup_ambiguous",
    ] = "composition_failed"
    individual_key_disclosed: Literal[False] = False
    value_disclosed: Literal[False] = False
    length_disclosed: Literal[False] = False
    progress_count_disclosed: Literal[False] = False
    source_read_calls_disclosed: Literal[False] = False
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def build_m86al_public_diagnostic(
    category: Literal["none"] | PublicFailureCategory,
) -> M86ALPublicAggregateDiagnostic:
    if category == "none":
        return M86ALPublicAggregateDiagnostic(state="FIT", failure_category="none")
    if category not in PUBLIC_FAILURE_CATEGORIES:
        category = "composition_failed"
    return M86ALPublicAggregateDiagnostic(
        state="NO-GO",
        failure_category=cast(PublicFailureCategory, category),
    )


__all__ = [
    "M86ALPublicAggregateDiagnostic",
    "PUBLIC_FAILURE_CATEGORIES",
    "build_m86al_public_diagnostic",
]
