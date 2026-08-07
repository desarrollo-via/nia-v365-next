"""Runner one-shot, inerte e inyectable para la observación R0 por historial."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from enum import Enum
from typing import Awaitable, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_adapter import (
    HistoryR0SelectionStatus,
    select_controlled_history_message,
)
from .bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from .config import ConnectorSettings
from .modes import ConnectorMode


CONTROLLED_CHAT_ID = 78733
CONTROLLED_DIALOG_ID = "chat78733"
STANDARD_WAIT_SECONDS = 180
ABSOLUTE_MAX_WAIT_SECONDS = 300
STANDARD_POLL_SECONDS = 5
ABSOLUTE_MAX_POLLS = 60
_ALLOWED_DIALOG_ROLES = {"client", "guest", "user"}


class BitrixHistoryReader(Protocol):
    async def get_dialog(self, dialog_id: str) -> BitrixHistoryReadResult: ...
    async def get_session_history(self, session_id: int) -> BitrixHistoryReadResult: ...
    async def close(self) -> None: ...


class BitrixHistoryR0Status(str, Enum):
    READY = "READY"
    RECEIVED = "RECEIVED"
    NO_GO = "NO-GO"


class BitrixHistoryR0Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: BitrixHistoryR0Status
    reason: str
    dialog_read_calls: int = Field(ge=0)
    history_read_calls: int = Field(ge=0)
    mutation_calls: int = Field(default=0, ge=0, le=0)
    dialog_verified: bool = False
    session_verified: bool = False
    baseline_captured: bool = False
    new_last_message_detected: bool = False
    candidate_count: int = Field(default=0, ge=0)
    controlled_message_verified: bool = False
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    resources_closed: bool = False


def _result(reason: str, **updates: object) -> BitrixHistoryR0Result:
    payload: dict[str, object] = {
        "status": BitrixHistoryR0Status.NO_GO,
        "reason": reason,
        "dialog_read_calls": 0,
        "history_read_calls": 0,
    }
    payload.update(updates)
    return BitrixHistoryR0Result(**payload)


def _barriers_safe(settings: ConnectorSettings) -> bool:
    return (
        settings.requested_mode == ConnectorMode.OFF.value
        and settings.effective_mode is ConnectorMode.OFF
        and settings.activation_locked
        and not settings.external_calls_enabled
        and not settings.pilot_enabled
        and settings.pilot_emergency_stop
        and settings.pilot_configuration_valid
    )


def _verified_dialog(dialog: BitrixHistoryDialog | None) -> bool:
    return bool(
        dialog is not None
        and dialog.id == CONTROLLED_CHAT_ID
        and dialog.dialog_id == CONTROLLED_DIALOG_ID
        and dialog.entity_type.upper() == "LINES"
        and dialog.role.strip().lower() in _ALLOWED_DIALOG_ROLES
        and dialog.last_message_id > 0
    )


async def _run_bitrix_history_r0_once(
    *,
    client: BitrixHistoryReader,
    settings: ConnectorSettings,
    expected_text_sha256: str,
    window_start: datetime,
    wait_seconds: int = STANDARD_WAIT_SECONDS,
    poll_seconds: int = STANDARD_POLL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> BitrixHistoryR0Result:
    """Ejecuta como máximo una lectura de historial y siempre cierra el cliente."""
    result = _result("bitrix_history_runner_not_started")
    try:
        if not _barriers_safe(settings):
            result = _result("bitrix_history_barrier_degraded")
            return result
        if (
            window_start.tzinfo is None
            or window_start.utcoffset() is None
            or wait_seconds <= 0
            or wait_seconds > ABSOLUTE_MAX_WAIT_SECONDS
            or poll_seconds < STANDARD_POLL_SECONDS
        ):
            result = _result("bitrix_history_window_invalid")
            return result
        poll_count = min(math.ceil(wait_seconds / poll_seconds), ABSOLUTE_MAX_POLLS)
        window_end = window_start + timedelta(seconds=wait_seconds)

        baseline_read = await client.get_dialog(CONTROLLED_DIALOG_ID)
        dialog_calls = 1
        baseline = baseline_read.dialog
        if (
            baseline_read.decision is not BitrixHistoryReadDecision.SUCCESS
            or not _verified_dialog(baseline)
        ):
            result = _result(
                baseline_read.error_code or "bitrix_history_dialog_mismatch",
                dialog_read_calls=dialog_calls,
            )
            return result
        try:
            session_id = baseline.session_id
        except ValueError:
            result = _result(
                "bitrix_history_session_identity_invalid",
                dialog_read_calls=dialog_calls,
                dialog_verified=True,
            )
            return result
        baseline_id = baseline.last_message_id

        for _ in range(poll_count):
            await sleep(poll_seconds)
            current_read = await client.get_dialog(CONTROLLED_DIALOG_ID)
            dialog_calls += 1
            current = current_read.dialog
            if (
                current_read.decision is not BitrixHistoryReadDecision.SUCCESS
                or not _verified_dialog(current)
            ):
                result = _result(
                    current_read.error_code or "bitrix_history_dialog_mismatch",
                    dialog_read_calls=dialog_calls,
                    dialog_verified=True,
                    session_verified=True,
                    baseline_captured=True,
                )
                return result
            try:
                current_session_id = current.session_id
            except ValueError:
                current_session_id = 0
            if current_session_id != session_id or current.last_message_id < baseline_id:
                result = _result(
                    "bitrix_history_dialog_drift",
                    dialog_read_calls=dialog_calls,
                    dialog_verified=True,
                    session_verified=True,
                    baseline_captured=True,
                )
                return result
            if current.last_message_id == baseline_id:
                continue

            history_read = await client.get_session_history(session_id)
            if (
                history_read.decision is not BitrixHistoryReadDecision.SUCCESS
                or history_read.history is None
            ):
                result = _result(
                    history_read.error_code or "bitrix_history_read_failed",
                    dialog_read_calls=dialog_calls,
                    history_read_calls=1,
                    dialog_verified=True,
                    session_verified=True,
                    baseline_captured=True,
                    new_last_message_detected=True,
                )
                return result
            selection = select_controlled_history_message(
                history=history_read.history,
                expected_chat_id=CONTROLLED_CHAT_ID,
                expected_dialog_id=CONTROLLED_DIALOG_ID,
                expected_session_id=session_id,
                baseline_message_id=baseline_id,
                expected_text_sha256=expected_text_sha256,
                window_start=window_start,
                window_end=window_end,
            )
            received = selection.status is HistoryR0SelectionStatus.SELECTED
            result = BitrixHistoryR0Result(
                status=(
                    BitrixHistoryR0Status.RECEIVED
                    if received
                    else BitrixHistoryR0Status.NO_GO
                ),
                reason=selection.reason,
                dialog_read_calls=dialog_calls,
                history_read_calls=1,
                dialog_verified=True,
                session_verified=True,
                baseline_captured=True,
                new_last_message_detected=True,
                candidate_count=selection.candidate_count,
                controlled_message_verified=received,
            )
            return result

        result = _result(
            "bitrix_history_wait_timeout",
            dialog_read_calls=dialog_calls,
            dialog_verified=True,
            session_verified=True,
            baseline_captured=True,
        )
        return result
    except Exception:
        result = _result("bitrix_history_runner_failed")
        return result


async def execute_bitrix_history_r0_once(
    *,
    client: BitrixHistoryReader,
    settings: ConnectorSettings,
    expected_text_sha256: str,
    window_start: datetime,
    wait_seconds: int = STANDARD_WAIT_SECONDS,
    poll_seconds: int = STANDARD_POLL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> BitrixHistoryR0Result:
    """Ejecuta el flujo inerte y cierra los recursos antes de devolver estado."""
    result: BitrixHistoryR0Result | None = None
    close_failed = False
    try:
        result = await _run_bitrix_history_r0_once(
            client=client,
            settings=settings,
            expected_text_sha256=expected_text_sha256,
            window_start=window_start,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            sleep=sleep,
        )
    finally:
        try:
            await client.close()
        except Exception:
            close_failed = True
    if close_failed:
        return result.model_copy(
            update={
                "status": BitrixHistoryR0Status.NO_GO,
                "reason": "bitrix_history_resources_close_failed",
                "resources_closed": False,
            }
        )
    return result.model_copy(update={"resources_closed": True})
