"""Cierre estático M31 del readiness técnico del comando protegido R0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_final_composition_audit import (
    PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT,
    ProtectedSessionFinalCompositionAuditContract,
)


@dataclass(frozen=True)
class ProtectedSessionCommandReadinessClosureSnapshot:
    phase: str = "M31"
    state: Literal["READY-AWAITING-AUTHORIZATION", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_command_readiness_not_closed"
    m30_contract_consumed: bool = False
    technical_readiness_closed: bool = False
    owner_complete: bool = False
    command_available: bool = False
    command_indicator_static_only: bool = True
    owner_module_invocable: bool = False
    command_invocation_authorized: bool = False
    parser_calls: int = 0
    builder_calls: int = 0
    source_calls: int = 0
    materializer_calls: int = 0
    confirmation_calls: int = 0
    command_calls: int = 0
    external_calls: int = 0
    source_open_authorized: bool = False
    oauth_read_authorized: bool = False
    bitrix_read_authorized: bool = False
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


def _m30_contract_is_exact(
    contract: ProtectedSessionFinalCompositionAuditContract,
) -> bool:
    return (
        type(contract) is ProtectedSessionFinalCompositionAuditContract
        and contract.phase == "M30"
        and contract.state == "NO-GO"
        and contract.reason
        == "protected_history_session_final_composition_audited_dormant"
        and contract.probe_limit_per_case == 1
        and contract.confirmation_attempt_limit == 1
        and contract.confirmation_timeout_seconds == 300.0
        and contract.rejection_terminal is True
        and contract.timeout_terminal is True
        and contract.cancellation_terminal is True
        and contract.cleanup_required is True
        and contract.parser_real_enabled is False
        and contract.builder_real_enabled is False
        and contract.command_available is False
        and contract.source_open_authorized is False
        and contract.external_calls_authorized is False
        and contract.real_execution_authorized is False
        and contract.message_request_authorized is False
    )


def close_static_protected_session_command_readiness(
    *,
    audit_contract: ProtectedSessionFinalCompositionAuditContract = (
        PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT
    ),
) -> ProtectedSessionCommandReadinessClosureSnapshot:
    """Publica disponibilidad estática; no crea parser ni invoca el comando."""

    if not _m30_contract_is_exact(audit_contract):
        return ProtectedSessionCommandReadinessClosureSnapshot(
            reason="protected_history_session_command_readiness_contract_rejected"
        )
    return ProtectedSessionCommandReadinessClosureSnapshot(
        state="READY-AWAITING-AUTHORIZATION",
        reason="protected_history_session_command_available_static_only",
        m30_contract_consumed=True,
        technical_readiness_closed=True,
        owner_complete=True,
        command_available=True,
    )


__all__ = [
    "ProtectedSessionCommandReadinessClosureSnapshot",
    "close_static_protected_session_command_readiness",
]
