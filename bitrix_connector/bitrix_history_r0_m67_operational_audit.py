"""Auditoría M67 estática de los enlaces operativos ausentes en M62-M66."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


M67_MISSING_OPERATIONAL_LINKS = (
    "literal_input_owner_unbound",
    "combined_fresh_preflight_evidence_unbound",
    "post_anchor_history_to_exact_scope_unbound",
    "real_nia_sender_to_exact_scope_unbound",
    "real_bitrix_sender_to_exact_scope_unbound",
    "real_receipt_deleter_unbound",
    "post_delete_history_reader_unbound",
    "attention_and_waiting_message_boundary_unbound",
    "single_owner_cleanup_and_authorization_consumption_unbound",
)


@dataclass(frozen=True)
class M67OperationalAudit:
    phase: Literal["M67"] = "M67"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "m62_m66_operational_binding_incomplete"
    m62_exact_scope_present: Literal[True] = True
    m63_literals_present: Literal[True] = True
    m64_budgets_reconciled: Literal[True] = True
    m65_dormant_coordinator_present: Literal[True] = True
    m66_exact_parser_present: Literal[True] = True
    protected_preflight_components_present: Literal[True] = True
    nia_and_bitrix_dispatch_components_present: Literal[True] = True
    rollback_contract_and_injected_adapter_present: Literal[True] = True
    missing_operational_links: tuple[str, ...] = M67_MISSING_OPERATIONAL_LINKS
    missing_operational_link_count: Literal[9] = 9
    first_confirmation_request_ready: Literal[False] = False
    point_8_can_begin: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    message_request_authorized: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            self.missing_operational_links != M67_MISSING_OPERATIONAL_LINKS
            or len(self.missing_operational_links)
            != self.missing_operational_link_count
            or len(set(self.missing_operational_links))
            != self.missing_operational_link_count
        ):
            raise ValueError("m67_operational_audit_invalid")


def audit_m62_m66_operational_readiness() -> M67OperationalAudit:
    """Publica sólo el dictamen fijo; no inspecciona fuentes ni ejecuta enlaces."""

    return M67OperationalAudit()


__all__ = [
    "M67_MISSING_OPERATIONAL_LINKS",
    "M67OperationalAudit",
    "audit_m62_m66_operational_readiness",
]
