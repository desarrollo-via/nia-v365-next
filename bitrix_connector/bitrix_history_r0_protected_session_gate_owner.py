"""Owner exterior one-shot para consumir el gate materializado R0."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_execution_gate import (
    ProtectedHistorySessionExecutionGateSnapshot,
)
from .bitrix_history_r0_protected_session_plan_materializer import (
    MaterializedProtectedHistorySessionPlan,
)


ConfirmationReader = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class ProtectedHistorySessionGateOwnerSnapshot:
    state: Literal["RECEIVED", "CANCELLED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_gate_owner_not_started"
    take_calls: int = 0
    confirmation_calls: int = 0
    gate_calls: int = 0
    cleanup_calls: int = 0
    private_state_cleared: bool = True
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


async def execute_materialized_history_session_gate_once(
    *,
    materialized: MaterializedProtectedHistorySessionPlan,
    confirmation_reader: ConfirmationReader,
) -> ProtectedHistorySessionGateOwnerSnapshot:
    """Toma, confirma y ejecuta una vez; siempre limpia el materializador."""

    if type(materialized) is not MaterializedProtectedHistorySessionPlan or not callable(
        confirmation_reader
    ):
        return ProtectedHistorySessionGateOwnerSnapshot(
            reason="protected_history_session_gate_owner_dependency_invalid"
        )
    take_calls = 0
    confirmation_calls = 0
    gate_calls = 0
    try:
        take_calls = 1
        gate = materialized.take_gate_once()
        confirmation_calls = 1
        confirmation = await confirmation_reader()
        gate_calls = 1
        result = await gate.execute_once(confirmation)
        if type(result) is not ProtectedHistorySessionExecutionGateSnapshot:
            raise TypeError("protected_history_session_gate_owner_result_invalid")
        if (
            result.connector_locked_off is not True
            or result.persisted is not False
            or result.nia_called is not False
            or result.bitrix_written is not False
            or result.private_state_cleared is not True
        ):
            raise TypeError("protected_history_session_gate_owner_barrier_degraded")
        state = result.state
        if state not in ("RECEIVED", "CANCELLED", "NO-GO"):
            raise TypeError("protected_history_session_gate_owner_state_invalid")
        return ProtectedHistorySessionGateOwnerSnapshot(
            state=state,
            reason={
                "RECEIVED": "protected_history_session_gate_owner_received",
                "CANCELLED": "protected_history_session_gate_owner_cancelled",
                "NO-GO": "protected_history_session_gate_owner_no_go",
            }[state],
            take_calls=1,
            confirmation_calls=1,
            gate_calls=1,
            cleanup_calls=1,
            connector_locked_off=result.connector_locked_off,
            persisted=result.persisted,
            nia_called=result.nia_called,
            bitrix_written=result.bitrix_written,
        )
    except asyncio.CancelledError:
        raise
    except BaseException:
        return ProtectedHistorySessionGateOwnerSnapshot(
            reason="protected_history_session_gate_owner_failed_safe",
            take_calls=take_calls,
            confirmation_calls=confirmation_calls,
            gate_calls=gate_calls,
            cleanup_calls=1,
        )
    finally:
        materialized.clear()


__all__ = [
    "ConfirmationReader",
    "ProtectedHistorySessionGateOwnerSnapshot",
    "execute_materialized_history_session_gate_once",
]
