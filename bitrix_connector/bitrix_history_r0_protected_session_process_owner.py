"""Owner one-shot del proceso protegido R0, apagado por defecto y sin CLI."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
    ProtectedHistorySessionExecutionPlan,
    coordinate_protected_history_session_once,
)
from .bitrix_history_r0_protected_session_failure import (
    normalize_protected_session_failure_category,
)


SessionCoordinator = Callable[..., Awaitable[object]]


@dataclass(frozen=True)
class ProtectedHistorySessionProcessOwnerSnapshot:
    state: Literal["PREPARED", "RECEIVED", "CANCELLED", "NO-GO"] = "PREPARED"
    reason: str = "protected_history_session_process_owner_prepared"
    failure_category: str = "none"
    execution_requested: bool = False
    owner_attempts: int = 0
    coordinator_calls: int = 0
    launcher_compositions: int = 0
    adapter_compositions: int = 0
    entrypoint_calls: int = 0
    owner_builder_calls: int = 0
    confirmation_calls: int = 0
    reader_factory_calls: int = 0
    reader_calls: int = 0
    cleanup_calls: int = 0
    same_process_continuity_bound: bool = True
    default_execution_enabled: bool = False
    cli_available: bool = False
    private_state_cleared: bool = True
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


class PreparedProtectedHistorySessionProcessOwner:
    """Posee el coordinador sin poseer ni serializar plan, settings o ancla."""

    __slots__ = ("_attempted", "_coordinator", "_coordinator_calls")

    def __init__(self, *, coordinator: SessionCoordinator) -> None:
        self._coordinator = coordinator
        self._attempted = False
        self._coordinator_calls = 0

    def __repr__(self) -> str:
        return "PreparedProtectedHistorySessionProcessOwner(<redacted>)"

    def snapshot(self) -> ProtectedHistorySessionProcessOwnerSnapshot:
        return ProtectedHistorySessionProcessOwnerSnapshot(
            owner_attempts=int(self._attempted),
            coordinator_calls=self._coordinator_calls,
        )

    async def execute_once(
        self,
        *,
        execute: bool = False,
        plan: ProtectedHistorySessionExecutionPlan | None = None,
    ) -> ProtectedHistorySessionProcessOwnerSnapshot:
        """Ejecuta toda la sesión en esta coroutine sólo con activación explícita."""

        if not execute:
            return self.snapshot()
        if self._attempted:
            return ProtectedHistorySessionProcessOwnerSnapshot(
                state="NO-GO",
                reason="protected_history_session_process_owner_already_used",
                execution_requested=True,
                owner_attempts=1,
                coordinator_calls=self._coordinator_calls,
            )
        self._attempted = True
        if type(plan) is not ProtectedHistorySessionExecutionPlan:
            return ProtectedHistorySessionProcessOwnerSnapshot(
                state="NO-GO",
                reason="protected_history_session_process_owner_plan_invalid",
                execution_requested=True,
                owner_attempts=1,
            )

        try:
            self._coordinator_calls = 1
            result = await self._coordinator(execute=True, plan=plan)
            if type(result) is not ProtectedHistorySessionCoordinatorSnapshot:
                raise TypeError("protected_history_session_process_owner_result_invalid")
            if (
                result.execution_requested is not True
                or result.launcher_compositions != 1
                or result.adapter_compositions != 1
                or result.entrypoint_calls != 1
                or result.private_state_cleared is not True
                or result.connector_locked_off is not True
                or result.persisted is not False
                or result.nia_called is not False
                or result.bitrix_written is not False
                or result.state not in ("RECEIVED", "CANCELLED", "NO-GO")
            ):
                raise TypeError("protected_history_session_process_owner_barrier_degraded")
            return ProtectedHistorySessionProcessOwnerSnapshot(
                state=result.state,
                reason={
                    "RECEIVED": "protected_history_session_process_owner_received",
                    "CANCELLED": "protected_history_session_process_owner_cancelled",
                    "NO-GO": "protected_history_session_process_owner_no_go",
                }[result.state],
                failure_category=normalize_protected_session_failure_category(
                    result.failure_category,
                    fallback="other_safe_failure",
                ),
                execution_requested=True,
                owner_attempts=1,
                coordinator_calls=1,
                launcher_compositions=result.launcher_compositions,
                adapter_compositions=result.adapter_compositions,
                entrypoint_calls=result.entrypoint_calls,
                owner_builder_calls=result.owner_builder_calls,
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
            return ProtectedHistorySessionProcessOwnerSnapshot(
                state="NO-GO",
                reason="protected_history_session_process_owner_failed_safe",
                failure_category="owner_failed",
                execution_requested=True,
                owner_attempts=1,
                coordinator_calls=self._coordinator_calls,
            )


def compose_protected_history_session_process_owner(
    *,
    coordinator: SessionCoordinator = coordinate_protected_history_session_once,
) -> PreparedProtectedHistorySessionProcessOwner:
    """Compone el owner sin plan, fuente, recursos, clientes ni ejecución."""

    if not callable(coordinator):
        raise TypeError("protected_history_session_process_owner_dependency_invalid")
    return PreparedProtectedHistorySessionProcessOwner(coordinator=coordinator)


__all__ = [
    "PreparedProtectedHistorySessionProcessOwner",
    "ProtectedHistorySessionProcessOwnerSnapshot",
    "SessionCoordinator",
    "compose_protected_history_session_process_owner",
]
