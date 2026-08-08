"""Compuerta exterior one-shot para habilitar el coordinador protegido R0."""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
    ProtectedHistorySessionExecutionPlan,
    coordinate_protected_history_session_once,
)


PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION = (
    "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ"
)
SessionCoordinator = Callable[..., Awaitable[object]]


@dataclass(frozen=True)
class ProtectedHistorySessionExecutionGateSnapshot:
    state: Literal["PREPARED", "RECEIVED", "CANCELLED", "NO-GO"] = "PREPARED"
    reason: str = "protected_history_session_execution_gate_prepared"
    gate_attempts: int = 0
    coordinator_calls: int = 0
    execution_requested: bool = False
    launcher_compositions: int = 0
    adapter_compositions: int = 0
    entrypoint_calls: int = 0
    owner_builder_calls: int = 0
    settings_capture_calls: int = 0
    confirmation_calls: int = 0
    reader_factory_calls: int = 0
    reader_calls: int = 0
    cleanup_calls: int = 0
    private_state_cleared: bool = True
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


class PreparedProtectedHistorySessionExecutionGate:
    """Posee plan y coordinador sin exponerlos; acepta un único intento."""

    __slots__ = ("_attempted", "_coordinator", "_coordinator_calls", "_plan")

    def __init__(
        self,
        *,
        plan: ProtectedHistorySessionExecutionPlan,
        coordinator: SessionCoordinator,
    ) -> None:
        self._plan = plan
        self._coordinator = coordinator
        self._attempted = False
        self._coordinator_calls = 0

    def __repr__(self) -> str:
        return "PreparedProtectedHistorySessionExecutionGate(<redacted>)"

    def snapshot(self) -> ProtectedHistorySessionExecutionGateSnapshot:
        return ProtectedHistorySessionExecutionGateSnapshot(
            gate_attempts=int(self._attempted),
            coordinator_calls=self._coordinator_calls,
        )

    async def execute_once(
        self,
        confirmation: str,
    ) -> ProtectedHistorySessionExecutionGateSnapshot:
        if self._attempted:
            return ProtectedHistorySessionExecutionGateSnapshot(
                state="NO-GO",
                reason="protected_history_session_execution_gate_already_used",
                gate_attempts=1,
                coordinator_calls=self._coordinator_calls,
            )
        self._attempted = True
        if not isinstance(confirmation, str) or not hmac.compare_digest(
            confirmation,
            PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
        ):
            return ProtectedHistorySessionExecutionGateSnapshot(
                state="NO-GO",
                reason="protected_history_session_execution_gate_rejected",
                gate_attempts=1,
            )

        try:
            self._coordinator_calls = 1
            result = await self._coordinator(execute=True, plan=self._plan)
            if type(result) is not ProtectedHistorySessionCoordinatorSnapshot:
                raise TypeError("protected_history_session_execution_result_invalid")
            if (
                result.execution_requested is not True
                or result.launcher_compositions != 1
                or result.adapter_compositions != 1
                or result.entrypoint_calls != 1
                or result.connector_locked_off is not True
                or result.persisted is not False
                or result.nia_called is not False
                or result.bitrix_written is not False
                or result.private_state_cleared is not True
            ):
                raise TypeError("protected_history_session_execution_barrier_degraded")
            state = result.state
            if state not in ("RECEIVED", "CANCELLED", "NO-GO"):
                raise TypeError("protected_history_session_execution_state_invalid")
            reason = {
                "RECEIVED": "protected_history_session_execution_received",
                "CANCELLED": "protected_history_session_execution_cancelled",
                "NO-GO": "protected_history_session_execution_no_go",
            }[state]
            return ProtectedHistorySessionExecutionGateSnapshot(
                state=state,
                reason=reason,
                gate_attempts=1,
                coordinator_calls=1,
                execution_requested=True,
                launcher_compositions=result.launcher_compositions,
                adapter_compositions=result.adapter_compositions,
                entrypoint_calls=result.entrypoint_calls,
                owner_builder_calls=result.owner_builder_calls,
                settings_capture_calls=result.settings_capture_calls,
                confirmation_calls=result.confirmation_calls,
                reader_factory_calls=result.reader_factory_calls,
                reader_calls=result.reader_calls,
                cleanup_calls=result.cleanup_calls,
                private_state_cleared=result.private_state_cleared,
                connector_locked_off=result.connector_locked_off,
                persisted=result.persisted,
                nia_called=result.nia_called,
                bitrix_written=result.bitrix_written,
            )
        except asyncio.CancelledError:
            raise
        except BaseException:
            return ProtectedHistorySessionExecutionGateSnapshot(
                state="NO-GO",
                reason="protected_history_session_execution_gate_failed_safe",
                gate_attempts=1,
                coordinator_calls=self._coordinator_calls,
            )


def compose_protected_history_session_execution_gate(
    *,
    plan: ProtectedHistorySessionExecutionPlan,
    coordinator: SessionCoordinator = coordinate_protected_history_session_once,
) -> PreparedProtectedHistorySessionExecutionGate:
    """Compone sin ejecutar; el plan queda privado y redactado."""

    if type(plan) is not ProtectedHistorySessionExecutionPlan or not callable(
        coordinator
    ):
        raise TypeError("protected_history_session_execution_gate_dependency_invalid")
    return PreparedProtectedHistorySessionExecutionGate(
        plan=plan,
        coordinator=coordinator,
    )


__all__ = [
    "PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION",
    "PreparedProtectedHistorySessionExecutionGate",
    "ProtectedHistorySessionExecutionGateSnapshot",
    "SessionCoordinator",
    "compose_protected_history_session_execution_gate",
]
