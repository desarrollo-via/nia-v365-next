"""Compuerta M49 inerte para una futura autorización del diagnóstico existente."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_existing_diagnostic_adapter import (
    compose_injected_existing_history_diagnostic_adapter,
)


Dependency = Callable[..., object]


@dataclass(frozen=True)
class ExistingHistoryDiagnosticGateSnapshot:
    phase: Literal["M49"] = "M49"
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "bitrix_history_existing_gate_not_started"
    adapter_composer_bound: bool = False
    authorization_required: bool = True
    authorization_present: bool = False
    authorization_phrase_defined: bool = False
    authorization_reusable: bool = False
    source_bound: bool = False
    cli_available: bool = False
    command_available: bool = False
    real_execution_authorized: bool = False
    source_open_authorized: bool = False
    oauth_refresh_authorized: bool = False
    retry_authorized: bool = False
    human_message_required: bool = False
    waiting_message_allowed: bool = False
    dialog_read_budget: int = 1
    history_read_budget: int = 1
    adapter_composer_calls: int = 0
    adapter_execute_calls: int = 0
    dialog_read_calls: int = 0
    history_read_calls: int = 0
    wait_calls: int = 0
    message_requests: int = 0
    mutation_calls: int = 0
    external_calls: int = 0
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


class PreparedExistingHistoryDiagnosticGate:
    """Retiene la referencia del adaptador sin frase, fuente o método ejecutable."""

    __slots__ = ("_adapter_composer",)

    def __init__(self, *, adapter_composer: Dependency) -> None:
        self._adapter_composer = adapter_composer

    def __repr__(self) -> str:
        return "PreparedExistingHistoryDiagnosticGate(<redacted>)"


def compose_prepared_existing_history_diagnostic_gate(
    *,
    adapter_composer: Dependency = compose_injected_existing_history_diagnostic_adapter,
) -> PreparedExistingHistoryDiagnosticGate:
    """Enlaza el adaptador sin construirlo ni definir una autorización utilizable."""

    if not callable(adapter_composer):
        raise TypeError("bitrix_history_existing_gate_dependency_invalid")
    return PreparedExistingHistoryDiagnosticGate(
        adapter_composer=adapter_composer,
    )


def preview_prepared_existing_history_diagnostic_gate(
    *,
    compose_gate: Callable[
        [], PreparedExistingHistoryDiagnosticGate
    ] = compose_prepared_existing_history_diagnostic_gate,
) -> ExistingHistoryDiagnosticGateSnapshot:
    """Publica sólo el bloqueo; nunca invoca el adaptador ni acepta frases."""

    try:
        gate = compose_gate()
        if type(gate) is not PreparedExistingHistoryDiagnosticGate:
            raise TypeError("bitrix_history_existing_gate_invalid")
    except Exception:
        return ExistingHistoryDiagnosticGateSnapshot(
            reason="bitrix_history_existing_gate_failed_safe"
        )
    return ExistingHistoryDiagnosticGateSnapshot(
        state="PREPARED",
        reason="bitrix_history_existing_gate_awaiting_separate_authorization",
        adapter_composer_bound=True,
    )


__all__ = [
    "ExistingHistoryDiagnosticGateSnapshot",
    "PreparedExistingHistoryDiagnosticGate",
    "compose_prepared_existing_history_diagnostic_gate",
    "preview_prepared_existing_history_diagnostic_gate",
]
