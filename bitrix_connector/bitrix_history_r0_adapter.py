"""Selección hermética de un único mensaje controlado leído desde historial."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .bitrix_history_r0_client import BitrixSessionHistory
from .bitrix_history_r0_validated_selector import (
    ValidatedHistorySelectionStatus,
    select_exact_controlled_human_message,
)


BITRIX_HISTORY_R0_ORIGIN = "bitrix_history_r0"


class HistoryR0SelectionStatus(str, Enum):
    SELECTED = "selected"
    NO_GO = "NO-GO"


class HistoryR0Candidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Literal["bitrix_history_r0"] = BITRIX_HISTORY_R0_ORIGIN
    message_id: int = Field(gt=0)
    chat_id: int = Field(gt=0)
    dialog_id: str = Field(pattern=r"^chat[1-9][0-9]*$")
    text: SecretStr = Field(exclude=True, repr=False)


class HistoryR0SelectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: HistoryR0SelectionStatus
    reason: str
    candidate_count: int = Field(ge=0)
    candidate: Optional[HistoryR0Candidate] = Field(default=None, repr=False)


def select_controlled_history_message(
    *,
    history: BitrixSessionHistory,
    expected_chat_id: int,
    expected_dialog_id: str,
    expected_session_id: int,
    baseline_message_id: int,
    expected_text_sha256: str,
    window_start: datetime,
    window_end: datetime,
    expected_sender_id: Optional[int] = None,
) -> HistoryR0SelectionResult:
    """Adapta M52 conservando el contrato privado histórico del candidato."""
    try:
        selected = select_exact_controlled_human_message(
            history=history,
            expected_chat_id=expected_chat_id,
            expected_dialog_id=expected_dialog_id,
            expected_session_id=expected_session_id,
            expected_sender_id=expected_sender_id,
            baseline_message_id=baseline_message_id,
            expected_text_sha256=expected_text_sha256,
            window_start=window_start,
            window_end=window_end,
        )
    except ValueError as exc:
        raise ValueError("bitrix_history_selection_contract_invalid") from exc

    if selected.status is not ValidatedHistorySelectionStatus.SELECTED:
        reason = (
            "bitrix_history_identity_mismatch"
            if selected.reason == "bitrix_validated_history_identity_mismatch"
            else "bitrix_history_candidate_count_invalid"
        )
        return HistoryR0SelectionResult(
            status=HistoryR0SelectionStatus.NO_GO,
            reason=reason,
            candidate_count=selected.candidate_count,
        )
    message = selected.selected_message
    if message is None:
        raise TypeError("bitrix_history_selected_message_missing")
    return HistoryR0SelectionResult(
        status=HistoryR0SelectionStatus.SELECTED,
        reason="bitrix_history_controlled_message_verified",
        candidate_count=1,
        candidate=HistoryR0Candidate(
            message_id=message.id,
            chat_id=expected_chat_id,
            dialog_id=expected_dialog_id,
            text=SecretStr(message.text),
        ),
    )
