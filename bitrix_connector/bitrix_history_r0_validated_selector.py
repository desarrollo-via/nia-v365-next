"""Selector puro M52 sobre un historial Bitrix previamente validado."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_client import BitrixHistoryMessage, BitrixSessionHistory


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ValidatedHistorySelectionStatus(str, Enum):
    SELECTED = "selected"
    NO_GO = "NO-GO"


class ValidatedHistorySelectionResult(BaseModel):
    """Salida pública sin texto, hash, ventana, identidades ni mensaje elegido."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M52"] = "M52"
    status: ValidatedHistorySelectionStatus
    reason: Literal[
        "bitrix_validated_history_identity_mismatch",
        "bitrix_controlled_human_candidate_count_invalid",
        "bitrix_controlled_human_message_verified",
    ]
    candidate_count: int = Field(ge=0)
    controlled_human_message_verified: bool
    selected_message: Optional[BitrixHistoryMessage] = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} debe incluir zona horaria")
    return value


def _is_system(message: BitrixHistoryMessage) -> bool:
    value = message.params.get("IS_SYSTEM", message.params.get("SYSTEM", False))
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "y", "yes"}
    return bool(value)


def _timestamp_in_window(
    message: BitrixHistoryMessage,
    *,
    start: datetime,
    end: datetime,
) -> bool:
    try:
        observed_at = datetime.fromisoformat(message.date.replace("Z", "+00:00"))
        _aware(observed_at, "message_date")
    except ValueError:
        return False
    return start <= observed_at <= end


def select_exact_controlled_human_message(
    *,
    history: BitrixSessionHistory,
    expected_chat_id: int,
    expected_dialog_id: str,
    expected_session_id: int,
    expected_sender_id: Optional[int] = None,
    baseline_message_id: int,
    expected_text_sha256: str,
    window_start: datetime,
    window_end: datetime,
) -> ValidatedHistorySelectionResult:
    """Cuenta sólo coincidencias humanas completas e ignora las demás entradas."""

    start = _aware(window_start, "window_start")
    end = _aware(window_end, "window_end")
    digest = expected_text_sha256.strip().lower()
    if (
        expected_chat_id <= 0
        or expected_dialog_id != f"chat{expected_chat_id}"
        or expected_session_id <= 0
        or (expected_sender_id is not None and expected_sender_id <= 0)
        or baseline_message_id <= 0
        or end <= start
        or not _SHA256_RE.fullmatch(digest)
    ):
        raise ValueError("bitrix_validated_history_selection_contract_invalid")

    if history.chat_id != expected_chat_id or history.session_id != expected_session_id:
        return ValidatedHistorySelectionResult(
            status=ValidatedHistorySelectionStatus.NO_GO,
            reason="bitrix_validated_history_identity_mismatch",
            candidate_count=0,
            controlled_human_message_verified=False,
        )

    users = {user.id: user for user in history.users}
    matches: list[BitrixHistoryMessage] = []
    for message in history.messages:
        author = users.get(message.senderid)
        identity_matches = (
            message.id > baseline_message_id
            and not _is_system(message)
            and message.chatid == expected_chat_id
            and message.recipientid == expected_dialog_id
            and (
                expected_sender_id is None
                or message.senderid == expected_sender_id
            )
            and author is not None
            and author.connector
        )
        if not identity_matches or not message.text.strip():
            continue
        if not _timestamp_in_window(message, start=start, end=end):
            continue
        if not hmac.compare_digest(
            hashlib.sha256(message.text.encode("utf-8")).hexdigest(),
            digest,
        ):
            continue
        matches.append(message)

    if len(matches) != 1:
        return ValidatedHistorySelectionResult(
            status=ValidatedHistorySelectionStatus.NO_GO,
            reason="bitrix_controlled_human_candidate_count_invalid",
            candidate_count=len(matches),
            controlled_human_message_verified=False,
        )
    return ValidatedHistorySelectionResult(
        status=ValidatedHistorySelectionStatus.SELECTED,
        reason="bitrix_controlled_human_message_verified",
        candidate_count=1,
        controlled_human_message_verified=True,
        selected_message=matches[0],
    )


__all__ = [
    "ValidatedHistorySelectionResult",
    "ValidatedHistorySelectionStatus",
    "select_exact_controlled_human_message",
]
