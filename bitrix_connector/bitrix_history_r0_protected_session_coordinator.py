"""Coordinador real-ready apagado por defecto para la sesión protegida R0."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from .bitrix_history_r0_handoff import MAX_AUTHORIZATION_WAIT_SECONDS
from .bitrix_history_r0_protected_handoff_composition import (
    ProtectedHandoffContinuitySnapshot,
)
from .bitrix_history_r0_protected_session_adapter import (
    ProtectedHistorySessionDependencyAdapter,
    compose_private_protected_history_session_adapter,
)
from .bitrix_history_r0_protected_session_entrypoint import (
    ProtectedHistorySessionEntrypointSnapshot,
    execute_protected_history_session_entrypoint_once,
)
from .bitrix_history_r0_protected_session_launcher import (
    PreparedProtectedHistorySessionLauncher,
    compose_real_ready_protected_history_session_launcher,
)
from .bitrix_history_r0_runner import (
    BitrixHistoryR0WaitingMessageSnapshot,
    WaitingMessageSignal,
)
from .bitrix_history_r0_protected_session_failure import (
    normalize_protected_session_failure_category,
)


LauncherComposer = Callable[[], PreparedProtectedHistorySessionLauncher]
AdapterComposer = Callable[..., ProtectedHistorySessionDependencyAdapter]
SessionEntrypoint = Callable[..., Awaitable[object]]
ConfirmationReader = Callable[[], Awaitable[str]]
HistoryClientBuilder = Callable[..., object]


async def _ignore_waiting_message(
    _snapshot: BitrixHistoryR0WaitingMessageSnapshot,
) -> None:
    return None


@dataclass(frozen=True, repr=False)
class ProtectedHistorySessionExecutionPlan:
    dotenv_path: Path
    inputs: BitrixHistoryR0EphemeralInputs
    resources_factory: object
    preflight_client_builder: HistoryClientBuilder
    reader_client_builder: HistoryClientBuilder
    confirmation_reader: ConfirmationReader
    on_waiting_message: WaitingMessageSignal = _ignore_waiting_message
    preflight_timeout_seconds: float = 10.0
    authorization_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS
    reader_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS

    def __repr__(self) -> str:
        return "ProtectedHistorySessionExecutionPlan(<redacted>)"


@dataclass(frozen=True)
class ProtectedHistorySessionCoordinatorSnapshot:
    state: Literal["PREPARED", "RECEIVED", "CANCELLED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_coordinator_not_started"
    failure_category: str = "none"
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


def _no_go(
    *,
    execution_requested: bool,
    launcher_compositions: int,
    adapter_compositions: int,
    entrypoint_calls: int,
    adapter: ProtectedHistorySessionDependencyAdapter | None,
) -> ProtectedHistorySessionCoordinatorSnapshot:
    adapter_snapshot = adapter.snapshot() if adapter is not None else None
    return ProtectedHistorySessionCoordinatorSnapshot(
        reason="protected_history_session_coordinator_no_go",
        failure_category="coordinator_failed",
        execution_requested=execution_requested,
        launcher_compositions=launcher_compositions,
        adapter_compositions=adapter_compositions,
        entrypoint_calls=entrypoint_calls,
        owner_builder_calls=(
            adapter_snapshot.owner_builder_calls if adapter_snapshot else 0
        ),
        settings_capture_calls=(
            adapter_snapshot.settings_capture_calls if adapter_snapshot else 0
        ),
        reader_factory_calls=(
            adapter_snapshot.reader_factory_calls if adapter_snapshot else 0
        ),
        cleanup_calls=adapter_snapshot.cleanup_calls if adapter_snapshot else 0,
        private_state_cleared=bool(
            adapter_snapshot is None
            or (
                not adapter_snapshot.settings_retained
                and not adapter_snapshot.owner_retained
            )
        ),
    )


async def coordinate_protected_history_session_once(
    *,
    execute: bool = False,
    plan: ProtectedHistorySessionExecutionPlan | None = None,
    compose_launcher: LauncherComposer = (
        compose_real_ready_protected_history_session_launcher
    ),
    compose_adapter: AdapterComposer = (
        compose_private_protected_history_session_adapter
    ),
    session_entrypoint: SessionEntrypoint = (
        execute_protected_history_session_entrypoint_once
    ),
) -> ProtectedHistorySessionCoordinatorSnapshot:
    """En preview sólo enlaza M14; ejecutar exige un plan explícito completo."""

    launcher_compositions = 0
    adapter_compositions = 0
    entrypoint_calls = 0
    adapter: ProtectedHistorySessionDependencyAdapter | None = None
    try:
        launcher_compositions = 1
        launcher = compose_launcher()
        if type(launcher) is not PreparedProtectedHistorySessionLauncher:
            raise TypeError("protected_history_session_coordinator_launcher_invalid")
        if not execute:
            return ProtectedHistorySessionCoordinatorSnapshot(
                state="PREPARED",
                reason="protected_history_session_coordinator_prepared",
                launcher_compositions=1,
            )
        if type(plan) is not ProtectedHistorySessionExecutionPlan:
            raise TypeError("protected_history_session_coordinator_plan_invalid")

        adapter_compositions = 1
        adapter = compose_adapter(
            dotenv_path=plan.dotenv_path,
            inputs=plan.inputs,
            resources_factory=plan.resources_factory,
            preflight_client_builder=plan.preflight_client_builder,
            reader_client_builder=plan.reader_client_builder,
            on_waiting_message=plan.on_waiting_message,
            timeout_seconds=plan.preflight_timeout_seconds,
        )
        if type(adapter) is not ProtectedHistorySessionDependencyAdapter:
            raise TypeError("protected_history_session_coordinator_adapter_invalid")

        entrypoint_calls = 1
        result = await session_entrypoint(
            owner_builder=adapter.build_owner_once,
            confirmation_reader=plan.confirmation_reader,
            reader_factory=adapter.build_reader_once,
            execute=True,
            authorization_timeout_seconds=plan.authorization_timeout_seconds,
            reader_timeout_seconds=plan.reader_timeout_seconds,
            private_state_cleanup=adapter.clear_private_state,
        )
        if type(result) not in (
            ProtectedHandoffContinuitySnapshot,
            ProtectedHistorySessionEntrypointSnapshot,
        ):
            raise TypeError("protected_history_session_coordinator_result_invalid")

        adapter_snapshot = adapter.snapshot()
        private_state_cleared = bool(
            adapter_snapshot.cleanup_calls >= 1
            and not adapter_snapshot.settings_retained
            and not adapter_snapshot.owner_retained
        )
        connector_locked_off = bool(
            getattr(result, "connector_locked_off", True)
        )
        persisted = bool(getattr(result, "persisted", False))
        nia_called = bool(getattr(result, "nia_called", False))
        bitrix_written = bool(getattr(result, "bitrix_written", False))
        barriers_safe = bool(
            connector_locked_off
            and not persisted
            and not nia_called
            and not bitrix_written
        )
        received = bool(
            result.state == "RECEIVED"
            and private_state_cleared
            and barriers_safe
        )
        cancelled = bool(result.state == "CANCELLED" and private_state_cleared)
        state = "RECEIVED" if received else "CANCELLED" if cancelled else "NO-GO"
        reason = {
            "RECEIVED": "protected_history_session_coordinator_received",
            "CANCELLED": "protected_history_session_coordinator_cancelled",
            "NO-GO": "protected_history_session_coordinator_no_go",
        }[state]
        failure_category = (
            "none"
            if state == "RECEIVED"
            else normalize_protected_session_failure_category(
                getattr(result, "failure_category", None),
                fallback=(
                    "authorization_cancelled"
                    if state == "CANCELLED"
                    else "other_safe_failure"
                ),
            )
        )
        return ProtectedHistorySessionCoordinatorSnapshot(
            state=state,
            reason=reason,
            failure_category=failure_category,
            execution_requested=True,
            launcher_compositions=1,
            adapter_compositions=1,
            entrypoint_calls=1,
            owner_builder_calls=adapter_snapshot.owner_builder_calls,
            settings_capture_calls=adapter_snapshot.settings_capture_calls,
            confirmation_calls=int(getattr(result, "authorization_calls", 0)),
            reader_factory_calls=adapter_snapshot.reader_factory_calls,
            reader_calls=int(getattr(result, "reader_calls", 0)),
            cleanup_calls=adapter_snapshot.cleanup_calls,
            private_state_cleared=private_state_cleared,
            connector_locked_off=connector_locked_off,
            persisted=persisted,
            nia_called=nia_called,
            bitrix_written=bitrix_written,
        )
    except asyncio.CancelledError:
        if adapter is not None:
            adapter.clear_private_state()
        raise
    except BaseException:
        if adapter is not None:
            adapter.clear_private_state()
        return _no_go(
            execution_requested=execute,
            launcher_compositions=launcher_compositions,
            adapter_compositions=adapter_compositions,
            entrypoint_calls=entrypoint_calls,
            adapter=adapter,
        )


__all__ = [
    "AdapterComposer",
    "ConfirmationReader",
    "HistoryClientBuilder",
    "LauncherComposer",
    "ProtectedHistorySessionCoordinatorSnapshot",
    "ProtectedHistorySessionExecutionPlan",
    "SessionEntrypoint",
    "coordinate_protected_history_session_once",
]
