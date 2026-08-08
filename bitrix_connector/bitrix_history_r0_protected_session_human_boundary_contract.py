"""Contrato público M22 para la frontera humana exterior protegida R0."""

from __future__ import annotations

from dataclasses import dataclass

from .bitrix_history_r0_handoff import MAX_AUTHORIZATION_WAIT_SECONDS


@dataclass(frozen=True)
class ProtectedHistorySessionHumanBoundaryContract:
    phase: str = "M22"
    owner_call_limit: int = 1
    confirmation_read_limit: int = 1
    confirmation_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS
    literal_confirmation_required: bool = True
    allowed_states: tuple[str, ...] = ("RECEIVED", "CANCELLED", "NO-GO")
    allowed_reasons: tuple[str, ...] = (
        "protected_history_session_gate_owner_received",
        "protected_history_session_gate_owner_cancelled",
        "protected_history_session_gate_owner_no_go",
        "protected_history_session_gate_owner_failed_safe",
        "protected_history_session_gate_owner_dependency_invalid",
        "protected_history_session_gate_owner_not_started",
    )
    allowed_output_fields: tuple[str, ...] = (
        "state",
        "reason",
        "take_calls",
        "confirmation_calls",
        "gate_calls",
        "cleanup_calls",
        "private_state_cleared",
        "connector_locked_off",
        "persisted",
        "nia_called",
        "bitrix_written",
    )
    timeout_terminal: bool = True
    cancellation_terminal: bool = True
    cleanup_required: bool = True
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    real_source_configured: bool = False
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT = (
    ProtectedHistorySessionHumanBoundaryContract()
)


__all__ = [
    "PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT",
    "ProtectedHistorySessionHumanBoundaryContract",
]
