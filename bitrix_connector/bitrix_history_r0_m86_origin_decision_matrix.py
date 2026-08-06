"""Matriz M86-AB para elegir un origen futuro sin consultar ninguno."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class M86ABOriginOption:
    source_kind: Literal[
        "local-dotenv",
        "allowlisted-process-environment",
        "windows-credential-target",
        "app-settings",
    ]
    reads_persistent_file: bool
    requires_network: bool
    circular_with_missing_target: bool
    exact_key_access_without_enumeration_possible: bool
    rank: int
    decision: Literal["REJECTED", "RECOMMENDED-DESIGN"]


M86AB_ORIGIN_OPTIONS = (
    M86ABOriginOption(
        source_kind="allowlisted-process-environment",
        reads_persistent_file=False,
        requires_network=False,
        circular_with_missing_target=False,
        exact_key_access_without_enumeration_possible=True,
        rank=1,
        decision="RECOMMENDED-DESIGN",
    ),
    M86ABOriginOption(
        source_kind="local-dotenv",
        reads_persistent_file=True,
        requires_network=False,
        circular_with_missing_target=False,
        exact_key_access_without_enumeration_possible=True,
        rank=2,
        decision="REJECTED",
    ),
    M86ABOriginOption(
        source_kind="app-settings",
        reads_persistent_file=False,
        requires_network=True,
        circular_with_missing_target=False,
        exact_key_access_without_enumeration_possible=True,
        rank=3,
        decision="REJECTED",
    ),
    M86ABOriginOption(
        source_kind="windows-credential-target",
        reads_persistent_file=False,
        requires_network=False,
        circular_with_missing_target=True,
        exact_key_access_without_enumeration_possible=True,
        rank=4,
        decision="REJECTED",
    ),
)


@dataclass(frozen=True)
class M86ABOriginDecisionMatrix:
    phase: Literal["M86-AB"] = "M86-AB"
    state: Literal["RECOMMENDED-DESIGN-NO-GO"] = "RECOMMENDED-DESIGN-NO-GO"
    recommended_source: Literal["allowlisted-process-environment"] = (
        "allowlisted-process-environment"
    )
    rationale: Literal[
        "no_file_no_network_no_circular_target_exact_keys_only"
    ] = "no_file_no_network_no_circular_target_exact_keys_only"
    options: tuple[M86ABOriginOption, ...] = M86AB_ORIGIN_OPTIONS
    real_binding_present: Literal[False] = False
    aggregate_presence_known: Literal[False] = False
    aggregate_fit_known: Literal[False] = False
    current_real_read_budget: Literal[0] = 0
    environment_enumeration_allowed: Literal[False] = False
    fallback_allowed: Literal[False] = False
    external_injection_owner_required: Literal[True] = True
    exact_seven_key_reads_required: Literal[True] = True
    owned_bytearray_handoff_required: Literal[True] = True
    authorization_text_present: Literal[False] = False
    values_read: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            tuple(item.rank for item in self.options) != (1, 2, 3, 4)
            or sum(item.decision == "RECOMMENDED-DESIGN" for item in self.options) != 1
            or self.options[0].source_kind != self.recommended_source
        ):
            raise ValueError("m86ab_origin_decision_matrix_invalid")


def inspect_m86ab_origin_decision_matrix() -> M86ABOriginDecisionMatrix:
    return M86ABOriginDecisionMatrix()


__all__ = [
    "M86ABOriginDecisionMatrix",
    "M86ABOriginOption",
    "M86AB_ORIGIN_OPTIONS",
    "inspect_m86ab_origin_decision_matrix",
]
