"""Selección M86-Z de origen protegido y handoff agregado, sólo declarativa."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


@dataclass(frozen=True)
class M86ZOriginCandidate:
    source_kind: Literal[
        "local-dotenv",
        "process-environment",
        "windows-credential-target",
        "app-settings",
    ]
    local_implementation_state: str
    decision: Literal["REJECTED"] = "REJECTED"
    rejection_reason: str = "unspecified"
    current_read_budget: Literal[0] = 0

    def __post_init__(self) -> None:
        if not self.local_implementation_state or self.rejection_reason == "unspecified":
            raise ValueError("m86z_origin_candidate_invalid")


M86Z_ORIGIN_CANDIDATES = (
    M86ZOriginCandidate(
        source_kind="local-dotenv",
        local_implementation_state="allowlisted_reader_present",
        rejection_reason="current_scope_forbids_dotenv_access",
    ),
    M86ZOriginCandidate(
        source_kind="process-environment",
        local_implementation_state="separate_cli_loader_present",
        rejection_reason="m80_budget_zero_and_no_owned_buffer_handoff",
    ),
    M86ZOriginCandidate(
        source_kind="windows-credential-target",
        local_implementation_state="reader_present_record_unavailable",
        rejection_reason="destination_cannot_be_its_own_missing_source",
    ),
    M86ZOriginCandidate(
        source_kind="app-settings",
        local_implementation_state="no_local_protected_adapter",
        rejection_reason="current_scope_forbids_query_and_adapter_absent",
    ),
)


@dataclass(frozen=True)
class M86ZAggregateHandoffContract:
    required_names: tuple[str, ...] = PROTECTED_SETTING_NAMES
    exact_order_required: Literal[True] = True
    owned_bytearray_values_required: Literal[True] = True
    ownership_transfer_budget: Literal[1] = 1
    fit_probe_budget: Literal[1] = 1
    source_close_before_public_result: Literal[True] = True
    probe_consumes_and_zeroizes_all_buffers: Literal[True] = True
    fallback_allowed: Literal[False] = False
    multiple_sources_allowed: Literal[False] = False
    individual_presence_public: Literal[False] = False
    individual_lengths_public: Literal[False] = False
    aggregate_length_public: Literal[False] = False
    public_result: tuple[str, str] = ("FIT", "NO-GO")

    def __post_init__(self) -> None:
        if (
            self.required_names != PROTECTED_SETTING_NAMES
            or len(self.required_names) != len(set(self.required_names))
            or self.public_result != ("FIT", "NO-GO")
        ):
            raise ValueError("m86z_handoff_contract_invalid")


@dataclass(frozen=True)
class M86ZProtectedOriginSelectionContract:
    phase: Literal["M86-Z"] = "M86-Z"
    state: Literal["NO-GO"] = "NO-GO"
    reason: Literal["no_eligible_protected_origin"] = "no_eligible_protected_origin"
    candidates: tuple[M86ZOriginCandidate, ...] = M86Z_ORIGIN_CANDIDATES
    selected_source: None = None
    handoff: M86ZAggregateHandoffContract = M86ZAggregateHandoffContract()
    default_source_allowed: Literal[False] = False
    fallback_allowed: Literal[False] = False
    source_reads: Literal[0] = 0
    values_loaded: Literal[False] = False
    real_authorization_literals_present: Literal[False] = False
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        expected = (
            "local-dotenv",
            "process-environment",
            "windows-credential-target",
            "app-settings",
        )
        if (
            tuple(item.source_kind for item in self.candidates) != expected
            or any(item.decision != "REJECTED" for item in self.candidates)
            or any(item.current_read_budget != 0 for item in self.candidates)
        ):
            raise ValueError("m86z_origin_selection_contract_invalid")


def inspect_m86z_protected_origin_selection(
) -> M86ZProtectedOriginSelectionContract:
    return M86ZProtectedOriginSelectionContract()


__all__ = [
    "M86ZAggregateHandoffContract",
    "M86ZOriginCandidate",
    "M86ZProtectedOriginSelectionContract",
    "M86Z_ORIGIN_CANDIDATES",
    "inspect_m86z_protected_origin_selection",
]
