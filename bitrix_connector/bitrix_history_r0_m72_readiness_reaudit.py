"""Reauditoría M72 estática del inventario M67 después de M68-M71."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m67_operational_audit import M67_MISSING_OPERATIONAL_LINKS


M72_CLOSED_LINKS = (
    "combined_fresh_preflight_evidence_unbound",
    "post_anchor_history_to_exact_scope_unbound",
)

M72_FIXTURE_PREPARED_REAL_LINKS = (
    "real_nia_sender_to_exact_scope_unbound",
    "real_bitrix_sender_to_exact_scope_unbound",
    "real_receipt_deleter_unbound",
    "post_delete_history_reader_unbound",
)

M72_STILL_UNBOUND_LOGICAL_LINKS = (
    "literal_input_owner_unbound",
    "attention_and_waiting_message_boundary_unbound",
    "single_owner_cleanup_and_authorization_consumption_unbound",
)

M72_FORMAL_REMAINING_LINKS = tuple(
    link for link in M67_MISSING_OPERATIONAL_LINKS if link not in M72_CLOSED_LINKS
)

M72_MINIMUM_REMAINING_PHASES = (
    "m73_single_owner_literal_attention_and_cleanup_fixture_only",
    "point_8_two_precise_confirmations_with_fresh_preflight",
    "single_authorized_real_roundtrip_with_exact_rollback",
)


@dataclass(frozen=True)
class M72ReadinessReaudit:
    phase: Literal["M72"] = "M72"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "m68_m71_safe_seams_present_real_owner_binding_incomplete"
    original_m67_link_count: Literal[9] = 9
    closed_links: tuple[str, ...] = M72_CLOSED_LINKS
    closed_link_count: Literal[2] = 2
    fixture_prepared_real_links: tuple[str, ...] = M72_FIXTURE_PREPARED_REAL_LINKS
    fixture_prepared_real_link_count: Literal[4] = 4
    still_unbound_logical_links: tuple[str, ...] = M72_STILL_UNBOUND_LOGICAL_LINKS
    still_unbound_logical_link_count: Literal[3] = 3
    formal_remaining_links: tuple[str, ...] = M72_FORMAL_REMAINING_LINKS
    formal_remaining_link_count: Literal[7] = 7
    composition_chain: tuple[str, ...] = ("M68", "M69", "M70", "M71")
    composition_chain_linear: Literal[True] = True
    redundant_new_adapter_layers_detected: Literal[False] = False
    additional_fixture_adapter_layer_needed: Literal[False] = False
    minimum_remaining_phases: tuple[str, ...] = M72_MINIMUM_REMAINING_PHASES
    next_minimum_phase: Literal[
        "m73_single_owner_literal_attention_and_cleanup_fixture_only"
    ] = "m73_single_owner_literal_attention_and_cleanup_fixture_only"
    first_confirmation_request_ready: Literal[False] = False
    point_8_can_begin: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    message_request_authorized: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        groups = (
            self.closed_links,
            self.fixture_prepared_real_links,
            self.still_unbound_logical_links,
        )
        flattened = tuple(link for group in groups for link in group)
        if (
            len(self.closed_links) != self.closed_link_count
            or len(self.fixture_prepared_real_links)
            != self.fixture_prepared_real_link_count
            or len(self.still_unbound_logical_links)
            != self.still_unbound_logical_link_count
            or len(flattened) != self.original_m67_link_count
            or set(flattened) != set(M67_MISSING_OPERATIONAL_LINKS)
            or len(set(flattened)) != self.original_m67_link_count
            or self.formal_remaining_links != M72_FORMAL_REMAINING_LINKS
            or len(self.formal_remaining_links) != self.formal_remaining_link_count
            or self.minimum_remaining_phases != M72_MINIMUM_REMAINING_PHASES
        ):
            raise ValueError("m72_readiness_reaudit_invalid")


def reaudit_m67_after_m68_m71() -> M72ReadinessReaudit:
    """Devuelve el ledger fijo y redactado; no inspecciona ni ejecuta fuentes."""

    return M72ReadinessReaudit()


__all__ = [
    "M72_CLOSED_LINKS",
    "M72_FIXTURE_PREPARED_REAL_LINKS",
    "M72_FORMAL_REMAINING_LINKS",
    "M72_MINIMUM_REMAINING_PHASES",
    "M72_STILL_UNBOUND_LOGICAL_LINKS",
    "M72ReadinessReaudit",
    "reaudit_m67_after_m68_m71",
]
