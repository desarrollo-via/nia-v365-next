"""Entrypoint inyectable y apagado por defecto para el owner protegido R0."""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Union

from .bitrix_history_r0_handoff import (
    MAX_AUTHORIZATION_WAIT_SECONDS,
    ArmedReader,
    BitrixHistoryR0HandoffDecision,
)
from .bitrix_history_r0_handoff_cli import HISTORY_R0_ARM_CONFIRMATION
from .bitrix_history_r0_protected_handoff_composition import (
    ProtectedHandoffContinuitySnapshot,
    ProtectedInMemoryHandoffOwner,
)


ProtectedOwnerBuilder = Callable[[], Awaitable[ProtectedInMemoryHandoffOwner]]
LiteralConfirmationReader = Callable[[], Awaitable[str]]
DeferredArmedReaderFactory = Callable[[], ArmedReader]
ProtectedSessionOutput = Union[
    "ProtectedHistorySessionEntrypointSnapshot",
    ProtectedHandoffContinuitySnapshot,
]
ProtectedSessionEmitter = Callable[[ProtectedSessionOutput], None]
PrivateStateCleanup = Callable[[], None]


@dataclass(frozen=True)
class ProtectedHistorySessionEntrypointSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "PREPARED"
    reason: str = "protected_history_session_prepared"
    failure_category: str = "none"
    execution_requested: bool = False
    owner_calls: int = 0
    confirmation_calls: int = 0
    reader_factory_calls: int = 0
    reader_calls: int = 0
    resources_closed: bool = True


def _ignore_output(_output: ProtectedSessionOutput) -> None:
    return None


def _ignore_cleanup() -> None:
    return None


def _entrypoint_no_go(
    *,
    owner_calls: int = 0,
    confirmation_calls: int = 0,
    reader_factory_calls: int = 0,
    reader_calls: int = 0,
    resources_closed: bool,
    failure_category: str = "entrypoint_failed",
) -> ProtectedHistorySessionEntrypointSnapshot:
    return ProtectedHistorySessionEntrypointSnapshot(
        state="NO-GO",
        reason="protected_history_session_no_go",
        failure_category=failure_category,
        execution_requested=True,
        owner_calls=owner_calls,
        confirmation_calls=confirmation_calls,
        reader_factory_calls=reader_factory_calls,
        reader_calls=reader_calls,
        resources_closed=resources_closed,
    )


async def execute_protected_history_session_entrypoint_once(
    *,
    owner_builder: ProtectedOwnerBuilder,
    confirmation_reader: LiteralConfirmationReader,
    reader_factory: DeferredArmedReaderFactory,
    execute: bool = False,
    authorization_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS,
    reader_timeout_seconds: float = MAX_AUTHORIZATION_WAIT_SECONDS,
    emit: ProtectedSessionEmitter = _ignore_output,
    private_state_cleanup: PrivateStateCleanup = _ignore_cleanup,
) -> ProtectedSessionOutput:
    """Compone la sesión sólo con ``execute=True``; el valor por defecto no actúa."""

    if not execute:
        prepared = ProtectedHistorySessionEntrypointSnapshot()
        emit(prepared)
        return prepared
    if (
        authorization_timeout_seconds <= 0
        or authorization_timeout_seconds > MAX_AUTHORIZATION_WAIT_SECONDS
        or reader_timeout_seconds <= 0
        or reader_timeout_seconds > MAX_AUTHORIZATION_WAIT_SECONDS
    ):
        blocked = _entrypoint_no_go(resources_closed=True)
        emit(blocked)
        return blocked

    owner: ProtectedInMemoryHandoffOwner | None = None
    owner_calls = 0
    confirmation_calls = 0
    reader_factory_calls = 0
    reader_calls = 0
    result: ProtectedSessionOutput
    try:
        owner_calls = 1
        owner = await owner_builder()
        if type(owner) is not ProtectedInMemoryHandoffOwner:
            raise TypeError("protected_history_session_owner_invalid")
        initial = owner.snapshot()
        emit(initial)
        if initial.state != "WAITING-AUTHORIZATION":
            return initial

        async def authorization_gate() -> BitrixHistoryR0HandoffDecision:
            nonlocal confirmation_calls
            confirmation_calls = 1
            received = await confirmation_reader()
            if hmac.compare_digest(received, HISTORY_R0_ARM_CONFIRMATION):
                return BitrixHistoryR0HandoffDecision.ARM
            return BitrixHistoryR0HandoffDecision.CANCEL

        authorized = await owner.wait_for_authorization(
            authorization_gate=authorization_gate,
            timeout_seconds=authorization_timeout_seconds,
        )
        emit(authorized)
        if authorized.state != "ARMED":
            return authorized

        reader_factory_calls = 1
        reader = reader_factory()
        if not callable(reader):
            raise TypeError("protected_history_session_reader_invalid")
        reader_calls = 1
        result = await asyncio.wait_for(
            owner.run_armed_reader_once(reader),
            timeout=reader_timeout_seconds,
        )
        emit(result)
        return result
    except asyncio.CancelledError:
        raise
    except Exception:
        result = _entrypoint_no_go(
            owner_calls=owner_calls,
            confirmation_calls=confirmation_calls,
            reader_factory_calls=reader_factory_calls,
            reader_calls=reader_calls,
            resources_closed=False,
            failure_category="entrypoint_failed",
        )
        emit(result)
        return result
    finally:
        close_failed = False
        if owner is not None:
            try:
                closed = await owner.close()
            except Exception:
                close_failed = True
            else:
                emit(closed)
                close_failed = bool(
                    closed.state != "CLOSED" or not closed.resources_closed
                )
        cleanup_failed = False
        try:
            cleanup_result = private_state_cleanup()
            if cleanup_result is not None:
                cleanup_failed = True
        except Exception:
            cleanup_failed = True
        if close_failed or cleanup_failed:
            failed = _entrypoint_no_go(
                owner_calls=owner_calls,
                confirmation_calls=confirmation_calls,
                reader_factory_calls=reader_factory_calls,
                reader_calls=reader_calls,
                resources_closed=False,
                failure_category="cleanup_failed",
            )
            emit(failed)
            raise RuntimeError("protected_history_session_close_failed") from None


__all__ = [
    "DeferredArmedReaderFactory",
    "LiteralConfirmationReader",
    "PrivateStateCleanup",
    "ProtectedHistorySessionEntrypointSnapshot",
    "ProtectedOwnerBuilder",
    "ProtectedSessionEmitter",
    "ProtectedSessionOutput",
    "execute_protected_history_session_entrypoint_once",
]
