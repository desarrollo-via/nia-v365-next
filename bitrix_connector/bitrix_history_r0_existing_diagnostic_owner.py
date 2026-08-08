"""Owner one-shot e inyectable para diagnosticar un historial R0 ya existente."""

from __future__ import annotations

from enum import Enum
from typing import Awaitable, Callable, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_client import (
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from .bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from .bitrix_history_r0_protected_reader_failure import (
    classify_protected_reader_failure,
)
from .bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
    _barriers_safe,
)
from .config import ConnectorSettings


class ExistingHistoryReader(Protocol):
    async def get_session_history(self, session_id: int) -> BitrixHistoryReadResult: ...
    async def close(self) -> None: ...


ExistingHistoryReaderFactory = Callable[[], Awaitable[ExistingHistoryReader]]
ExistingHistoryPreflightExecutor = Callable[
    [ConnectorSettings], Awaitable[BitrixHistoryR0PreflightOutcome]
]


class ExistingHistoryReaderFactoryError(RuntimeError):
    """Fallo allowlisted de fábrica con estado de cierre verificable."""

    _ALLOWED_REASONS = {
        "bitrix_history_read_failed",
        "bitrix_history_resources_close_failed",
    }

    def __init__(self, reason: str, *, resources_closed: bool) -> None:
        if reason not in self._ALLOWED_REASONS:
            raise ValueError("bitrix_history_reader_factory_reason_invalid")
        super().__init__(reason)
        self.reason = reason
        self.resources_closed = resources_closed


class ExistingHistoryDiagnosticState(str, Enum):
    PREPARED = "PREPARED"
    DIAGNOSED = "DIAGNOSED"
    NO_GO = "NO-GO"


class ExistingHistoryDiagnosticResult(BaseModel):
    """Salida pública cerrada; nunca contiene ancla, sesión ni mensajes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: ExistingHistoryDiagnosticState
    reason: str
    failure_category: Optional[str] = None
    dialog_read_calls: int = Field(default=0, ge=0, le=1)
    history_read_calls: int = Field(default=0, ge=0, le=1)
    mutation_calls: int = Field(default=0, ge=0, le=0)
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    resources_closed: bool = True


def _safe_result(
    state: ExistingHistoryDiagnosticState,
    reason: str,
    *,
    failure_category: Optional[str] = None,
    dialog_read_calls: int = 0,
    history_read_calls: int = 0,
    resources_closed: bool = True,
) -> ExistingHistoryDiagnosticResult:
    return ExistingHistoryDiagnosticResult(
        state=state,
        reason=reason,
        failure_category=failure_category,
        dialog_read_calls=dialog_read_calls,
        history_read_calls=history_read_calls,
        resources_closed=resources_closed,
    )


def _preflight_is_exactly_ready(outcome: object) -> bool:
    if type(outcome) is not BitrixHistoryR0PreflightOutcome:
        return False
    result = outcome.result
    return (
        result.status is BitrixHistoryR0Status.READY
        and result.reason == "bitrix_history_preflight_ready"
        and result.dialog_read_calls == 1
        and result.history_read_calls == 0
        and result.mutation_calls == 0
        and result.dialog_verified
        and result.session_verified
        and result.baseline_captured
        and result.connector_locked_off
        and not result.persisted
        and not result.nia_called
        and not result.bitrix_written
        and result.resources_closed
        and outcome.anchor_available
    )


def _safe_preflight_failure(outcome: object) -> tuple[str, str, int, bool]:
    if type(outcome) is not BitrixHistoryR0PreflightOutcome:
        return (
            "bitrix_history_preflight_contract_invalid",
            "reader_other_safe_failure",
            0,
            True,
        )
    result = outcome.result
    calls = min(result.dialog_read_calls, 1)
    return (
        result.reason,
        classify_protected_reader_failure(result),
        calls,
        result.resources_closed,
    )


async def execute_existing_history_diagnostic_once(
    *,
    execute: bool,
    settings: ConnectorSettings,
    preflight_executor: ExistingHistoryPreflightExecutor,
    history_reader_factory: ExistingHistoryReaderFactory,
) -> ExistingHistoryDiagnosticResult:
    """Prepara por defecto o realiza exactamente preflight + una lectura de historial."""

    if not execute:
        return _safe_result(
            ExistingHistoryDiagnosticState.PREPARED,
            "bitrix_history_existing_diagnostic_prepared",
        )

    if not _barriers_safe(settings):
        return _safe_result(
            ExistingHistoryDiagnosticState.NO_GO,
            "bitrix_history_barrier_degraded",
            failure_category="reader_barrier_degraded",
        )

    try:
        preflight = await preflight_executor(settings)
    except Exception:
        return _safe_result(
            ExistingHistoryDiagnosticState.NO_GO,
            "bitrix_history_preflight_failed_safe",
            failure_category="reader_failed",
        )

    if not _preflight_is_exactly_ready(preflight):
        reason, category, calls, resources_closed = _safe_preflight_failure(preflight)
        return _safe_result(
            ExistingHistoryDiagnosticState.NO_GO,
            reason,
            failure_category=category,
            dialog_read_calls=calls,
            resources_closed=resources_closed,
        )

    anchor: BitrixHistoryR0Anchor = preflight.require_anchor()
    reader: Optional[ExistingHistoryReader] = None
    read_result: Optional[BitrixHistoryReadResult] = None
    history_read_calls = 0
    reason = "bitrix_history_read_failed"
    resources_closed = True
    try:
        reader = await history_reader_factory()
        history_read_calls = 1
        read_result = await reader.get_session_history(anchor.session_id)
    except ExistingHistoryReaderFactoryError as exc:
        reason = exc.reason
        resources_closed = exc.resources_closed
    except Exception:
        pass
    finally:
        if reader is not None:
            try:
                await reader.close()
            except Exception:
                resources_closed = False

    if not resources_closed:
        return _safe_result(
            ExistingHistoryDiagnosticState.NO_GO,
            "bitrix_history_resources_close_failed",
            failure_category="reader_resources_close_failed",
            dialog_read_calls=1,
            history_read_calls=history_read_calls,
            resources_closed=False,
        )

    if type(read_result) is not BitrixHistoryReadResult:
        return _safe_result(
            ExistingHistoryDiagnosticState.NO_GO,
            reason,
            failure_category="reader_history_unavailable",
            dialog_read_calls=1,
            history_read_calls=history_read_calls,
        )

    if (
        read_result.decision is BitrixHistoryReadDecision.SUCCESS
        and read_result.history is not None
    ):
        return _safe_result(
            ExistingHistoryDiagnosticState.DIAGNOSED,
            "bitrix_history_existing_contract_valid",
            dialog_read_calls=1,
            history_read_calls=1,
        )

    failure = BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.NO_GO,
        reason=read_result.error_code or "bitrix_history_read_failed",
        dialog_read_calls=1,
        history_read_calls=1,
        resources_closed=True,
    )
    return _safe_result(
        ExistingHistoryDiagnosticState.NO_GO,
        failure.reason,
        failure_category=classify_protected_reader_failure(failure),
        dialog_read_calls=1,
        history_read_calls=1,
    )


__all__ = [
    "ExistingHistoryDiagnosticResult",
    "ExistingHistoryDiagnosticState",
    "ExistingHistoryPreflightExecutor",
    "ExistingHistoryReader",
    "ExistingHistoryReaderFactoryError",
    "ExistingHistoryReaderFactory",
    "execute_existing_history_diagnostic_once",
]
