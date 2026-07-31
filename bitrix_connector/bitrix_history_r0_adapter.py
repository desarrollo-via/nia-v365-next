"""Selección hermética de un único mensaje controlado leído desde historial."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .bitrix_history_r0_client import BitrixSessionHistory


BITRIX_HISTORY_R0_ORIGIN = "bitrix_history_r0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} debe incluir zona horaria")
    return value


def _is_system(params: dict[str, object]) -> bool:
    value = params.get("IS_SYSTEM", params.get("SYSTEM", False))
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "y", "yes"}
    return bool(value)


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
) -> HistoryR0SelectionResult:
    """Valida identidad y hash sin proyectar texto ni autor en el resultado."""
    start = _aware(window_start, "window_start")
    end = _aware(window_end, "window_end")
    digest = expected_text_sha256.strip().lower()
    if (
        expected_chat_id <= 0
        or expected_dialog_id != f"chat{expected_chat_id}"
        or expected_session_id <= 0
        or baseline_message_id <= 0
        or end <= start
        or not _SHA256_RE.fullmatch(digest)
    ):
        raise ValueError("bitrix_history_selection_contract_invalid")
    if history.chat_id != expected_chat_id or history.session_id != expected_session_id:
        return HistoryR0SelectionResult(
            status=HistoryR0SelectionStatus.NO_GO,
            reason="bitrix_history_identity_mismatch",
            candidate_count=0,
        )

    new_messages = tuple(
        message
        for message in history.messages
        if message.id > baseline_message_id and not _is_system(message.params)
    )
    if len(new_messages) != 1:
        return HistoryR0SelectionResult(
            status=HistoryR0SelectionStatus.NO_GO,
            reason="bitrix_history_candidate_count_invalid",
            candidate_count=len(new_messages),
        )

    message = new_messages[0]
    users = {user.id: user for user in history.users}
    author = users.get(message.senderid)
    try:
        observed_at = datetime.fromisoformat(message.date.replace("Z", "+00:00"))
        _aware(observed_at, "message_date")
    except ValueError:
        observed_at = None
    identity_valid = (
        message.chatid == expected_chat_id
        and message.recipientid == expected_dialog_id
        and author is not None
        and author.connector
        and observed_at is not None
        and start <= observed_at <= end
        and bool(message.text.strip())
    )
    hash_valid = hmac.compare_digest(
        hashlib.sha256(message.text.encode("utf-8")).hexdigest(),
        digest,
    )
    if not identity_valid or not hash_valid:
        return HistoryR0SelectionResult(
            status=HistoryR0SelectionStatus.NO_GO,
            reason="bitrix_history_controlled_message_mismatch",
            candidate_count=1,
        )
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
