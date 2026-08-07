"""Materialización privada one-shot del plan y gate protegidos R0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from .bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionExecutionPlan,
)
from .bitrix_history_r0_protected_session_execution_gate import (
    PreparedProtectedHistorySessionExecutionGate,
    compose_protected_history_session_execution_gate,
)


Dependency = Callable[..., object]


@dataclass(frozen=True)
class ProtectedHistorySessionPlanMaterializerSnapshot:
    state: Literal["READY", "TAKEN", "CLEARED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_plan_materializer_not_started"
    plan_calls: int = 0
    gate_calls: int = 0
    take_calls: int = 0
    cleanup_calls: int = 0
    plan_retained: bool = False
    gate_retained: bool = False
    external_calls: int = 0


class MaterializedProtectedHistorySessionPlan:
    """Posee plan y gate sin exponer inputs; entrega el gate una sola vez."""

    __slots__ = ("_cleanup_calls", "_gate", "_plan", "_take_calls")

    def __init__(
        self,
        *,
        plan: ProtectedHistorySessionExecutionPlan,
        gate: PreparedProtectedHistorySessionExecutionGate,
    ) -> None:
        self._plan = plan
        self._gate = gate
        self._take_calls = 0
        self._cleanup_calls = 0

    def __repr__(self) -> str:
        return "MaterializedProtectedHistorySessionPlan(<redacted>)"

    def snapshot(self) -> ProtectedHistorySessionPlanMaterializerSnapshot:
        if self._cleanup_calls:
            state = "CLEARED"
            reason = "protected_history_session_plan_materializer_cleared"
        elif self._take_calls:
            state = "TAKEN"
            reason = "protected_history_session_plan_materializer_taken"
        else:
            state = "READY"
            reason = "protected_history_session_plan_materializer_ready"
        return ProtectedHistorySessionPlanMaterializerSnapshot(
            state=state,
            reason=reason,
            plan_calls=1,
            gate_calls=1,
            take_calls=self._take_calls,
            cleanup_calls=self._cleanup_calls,
            plan_retained=self._plan is not None,
            gate_retained=self._gate is not None,
        )

    def take_gate_once(self) -> PreparedProtectedHistorySessionExecutionGate:
        if self._take_calls or self._gate is None:
            raise RuntimeError("protected_history_session_plan_gate_unavailable")
        self._take_calls = 1
        gate = self._gate
        self._gate = None
        self._plan = None
        return gate

    def clear(self) -> None:
        self._cleanup_calls += 1
        self._gate = None
        self._plan = None


def materialize_private_protected_history_session_plan_once(
    *,
    dotenv_path: Path,
    inputs: BitrixHistoryR0EphemeralInputs,
    resources_factory: object,
    preflight_client_builder: Dependency,
    reader_client_builder: Dependency,
    confirmation_reader: Dependency,
    preflight_timeout_seconds: float = 10.0,
    authorization_timeout_seconds: float = 300.0,
    reader_timeout_seconds: float = 300.0,
    plan_builder: Dependency = ProtectedHistorySessionExecutionPlan,
    gate_composer: Dependency = compose_protected_history_session_execution_gate,
) -> MaterializedProtectedHistorySessionPlan:
    """Construye plan y gate sin abrir la ruta ni invocar recursos o clientes."""

    if (
        type(inputs) is not BitrixHistoryR0EphemeralInputs
        or not callable(getattr(resources_factory, "build", None))
        or not callable(preflight_client_builder)
        or not callable(reader_client_builder)
        or not callable(confirmation_reader)
        or not callable(plan_builder)
        or not callable(gate_composer)
    ):
        raise TypeError("protected_history_session_plan_materializer_dependency_invalid")
    try:
        plan = plan_builder(
            dotenv_path=Path(dotenv_path),
            inputs=inputs,
            resources_factory=resources_factory,
            preflight_client_builder=preflight_client_builder,
            reader_client_builder=reader_client_builder,
            confirmation_reader=confirmation_reader,
            preflight_timeout_seconds=preflight_timeout_seconds,
            authorization_timeout_seconds=authorization_timeout_seconds,
            reader_timeout_seconds=reader_timeout_seconds,
        )
        if type(plan) is not ProtectedHistorySessionExecutionPlan:
            raise TypeError("protected_history_session_plan_materializer_plan_invalid")
        gate = gate_composer(plan=plan)
        if type(gate) is not PreparedProtectedHistorySessionExecutionGate:
            raise TypeError("protected_history_session_plan_materializer_gate_invalid")
    except Exception as exc:
        raise RuntimeError("protected_history_session_plan_materializer_failed_safe") from None
    return MaterializedProtectedHistorySessionPlan(plan=plan, gate=gate)


__all__ = [
    "MaterializedProtectedHistorySessionPlan",
    "ProtectedHistorySessionPlanMaterializerSnapshot",
    "materialize_private_protected_history_session_plan_once",
]
