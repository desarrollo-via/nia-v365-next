"""Owner M86-AM fixture-only para recorrer categorías agregadas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_public_aggregate_diagnostic import (
    M86ALPublicAggregateDiagnostic,
    build_m86al_public_diagnostic,
)


@dataclass(frozen=True)
class M86AMFixtureOperations:
    authorization_exact: bool = True
    source_stage: Literal["ready", "factory_failed", "open_failed", "transfer_failed"] = (
        "ready"
    )
    candidate_stage: Literal["fit", "not_fit", "composition_failed"] = "fit"
    cleanup_verified: bool = True


class M86AMFixtureDiagnosticOwner:
    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used = False

    def run_once(
        self,
        *,
        operations: M86AMFixtureOperations,
    ) -> M86ALPublicAggregateDiagnostic:
        if self._used or type(operations) is not M86AMFixtureOperations:
            self._used = True
            raise RuntimeError("m86am_owner_reuse_or_operations_invalid")
        self._used = True
        category = "none"
        if not operations.authorization_exact:
            category = "authorization_invalid"
        elif operations.source_stage != "ready":
            category = "source_aggregate_unavailable"
        elif operations.candidate_stage == "not_fit":
            category = "candidate_not_fit"
        elif operations.candidate_stage == "composition_failed":
            category = "composition_failed"
        if not operations.cleanup_verified:
            category = "cleanup_ambiguous"
        return build_m86al_public_diagnostic(category)


__all__ = ["M86AMFixtureDiagnosticOwner", "M86AMFixtureOperations"]
