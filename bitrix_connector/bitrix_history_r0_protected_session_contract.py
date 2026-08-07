"""Contrato público congelado para la sesión protegida R0."""

from __future__ import annotations

from dataclasses import dataclass

from .bitrix_history_r0_handoff import MAX_AUTHORIZATION_WAIT_SECONDS
from .bitrix_history_r0_preflight_composition import (
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
)


@dataclass(frozen=True)
class ProtectedHistorySessionContract:
    phase: str = "M18"
    execute_default: bool = False
    explicit_plan_required: bool = True
    outer_confirmation_required: bool = True
    inner_confirmation_required: bool = True
    gate_attempt_limit: int = 1
    coordinator_attempt_limit: int = 1
    owner_attempt_limit: int = 1
    preflight_attempt_limit: int = 1
    reader_attempt_limit: int = 1
    preflight_timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS
    authorization_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS
    reader_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS
    baseline_dialog_reads: int = 1
    baseline_history_reads: int = 0
    mutation_calls: int = 0
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    cleanup_required: bool = True
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


PROTECTED_HISTORY_SESSION_CONTRACT = ProtectedHistorySessionContract()


__all__ = [
    "PROTECTED_HISTORY_SESSION_CONTRACT",
    "ProtectedHistorySessionContract",
]
