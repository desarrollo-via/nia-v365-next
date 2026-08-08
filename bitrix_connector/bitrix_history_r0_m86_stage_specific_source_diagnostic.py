"""Diagnóstico público M86-AS por etapa, sin evidencia individual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast


M86AS_SOURCE_FAILURE_CATEGORIES = (
    "source_factory_unavailable",
    "source_open_unavailable",
    "source_transfer_unavailable",
)

M86AS_PUBLIC_CATEGORIES = (
    "authorization_invalid",
    *M86AS_SOURCE_FAILURE_CATEGORIES,
    "cleanup_ambiguous",
)

M86ASPublicCategory = Literal[
    "none",
    "authorization_invalid",
    "source_factory_unavailable",
    "source_open_unavailable",
    "source_transfer_unavailable",
    "cleanup_ambiguous",
]


@dataclass(frozen=True)
class M86ASStageSpecificSourceDiagnostic:
    phase: Literal["M86-AS"] = "M86-AS"
    state: Literal["SOURCE-READY", "NO-GO"] = "NO-GO"
    failure_category: M86ASPublicCategory = "authorization_invalid"
    individual_key_disclosed: Literal[False] = False
    value_disclosed: Literal[False] = False
    length_disclosed: Literal[False] = False
    progress_count_disclosed: Literal[False] = False
    source_read_calls_disclosed: Literal[False] = False
    real_source_bound: Literal[False] = False
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def build_m86as_source_diagnostic(
    category: M86ASPublicCategory,
) -> M86ASStageSpecificSourceDiagnostic:
    if category == "none":
        return M86ASStageSpecificSourceDiagnostic(
            state="SOURCE-READY",
            failure_category="none",
        )
    if category not in M86AS_PUBLIC_CATEGORIES:
        category = "authorization_invalid"
    return M86ASStageSpecificSourceDiagnostic(
        failure_category=cast(M86ASPublicCategory, category)
    )


__all__ = [
    "M86AS_PUBLIC_CATEGORIES",
    "M86AS_SOURCE_FAILURE_CATEGORIES",
    "M86ASPublicCategory",
    "M86ASStageSpecificSourceDiagnostic",
    "build_m86as_source_diagnostic",
]
