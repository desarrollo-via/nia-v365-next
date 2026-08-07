"""Contrato M57 del rollback de una respuesta propia, sin cliente ni red."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


BITRIX_REPLY_DELETE_METHOD = "imbot.v2.Chat.Message.delete"


class ReplyRollbackStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"


class ReplyRollbackDeletePreview(BaseModel):
    """Payload sin auth para borrar completamente sólo la respuesta recibida."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal[
        "imbot.v2.Chat.Message.delete"
    ] = BITRIX_REPLY_DELETE_METHOD
    botId: int = Field(gt=0)
    messageId: int = Field(gt=0)
    complete: Literal[True] = True


class ReplyRollbackFixtureResult(BaseModel):
    """Evidencia pública sin IDs, historial, textos ni respuesta externa."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M57"] = "M57"
    status: ReplyRollbackStatus
    reason: Literal[
        "reply_rollback_fixture_verified",
        "reply_rollback_delete_response_invalid",
        "reply_rollback_history_response_invalid",
        "reply_rollback_history_identity_mismatch",
        "reply_rollback_target_still_present",
    ]
    official_method_identified: Literal[True] = True
    official_owner_bot_required: Literal[True] = True
    official_complete_deletion_selected: Literal[True] = True
    official_success_requires_nested_true: Literal[True] = True
    verification_uses_session_history_absence: Literal[True] = True
    verification_strategy_is_documented_contract_inference: Literal[True] = True
    fixture_delete_response_accepted: bool = False
    fixture_target_absent_after_delete: bool = False
    rollback_contract_locally_tested: bool = False
    real_rollback_composed: Literal[False] = False
    real_rollback_executed: Literal[False] = False
    real_portal_behavior_verified: Literal[False] = False
    fixture_only: Literal[True] = True
    delete_calls: int = Field(default=0, ge=0, le=0)
    history_read_calls: int = Field(default=0, ge=0, le=0)
    external_calls: int = Field(default=0, ge=0, le=0)
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def build_reply_rollback_delete_preview(
    *,
    bot_id: int,
    sent_message_id: int,
) -> ReplyRollbackDeletePreview:
    """Deriva el único objetivo desde el ID devuelto por el envío futuro."""

    return ReplyRollbackDeletePreview(
        botId=bot_id,
        messageId=sent_message_id,
    )


def _positive_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean id")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid id") from exc
    if normalized <= 0 or str(normalized) != str(value).strip():
        raise ValueError("invalid id")
    return normalized


def _result(
    reason: str,
    *,
    delete_accepted: bool = False,
) -> ReplyRollbackFixtureResult:
    return ReplyRollbackFixtureResult(
        status=ReplyRollbackStatus.NO_GO,
        reason=reason,
        fixture_delete_response_accepted=delete_accepted,
    )


def reply_delete_response_is_success(response: object) -> bool:
    """Reconoce sólo el recibo oficial anidado y sin campos ambiguos."""

    if not isinstance(response, Mapping):
        return False
    root = response.get("result")
    return (
        isinstance(root, Mapping)
        and root.get("result") is True
        and len(root) == 1
    )


def verify_reply_rollback_fixture(
    *,
    preview: ReplyRollbackDeletePreview,
    delete_response: object,
    post_delete_history_response: object,
    expected_chat_id: int,
    expected_session_id: int,
) -> ReplyRollbackFixtureResult:
    """Valida recibo de borrado y ausencia posterior en historial fixture."""

    if (
        expected_chat_id <= 0
        or expected_session_id <= 0
        or not isinstance(preview, ReplyRollbackDeletePreview)
    ):
        raise ValueError("reply_rollback_contract_invalid")

    if not reply_delete_response_is_success(delete_response):
        return _result("reply_rollback_delete_response_invalid")

    if not isinstance(post_delete_history_response, Mapping):
        return _result(
            "reply_rollback_history_response_invalid",
            delete_accepted=True,
        )
    history = post_delete_history_response.get("result")
    if not isinstance(history, Mapping):
        return _result(
            "reply_rollback_history_response_invalid",
            delete_accepted=True,
        )
    try:
        chat_id = _positive_int(history.get("chatId"))
        session_id = _positive_int(history.get("sessionId"))
    except ValueError:
        return _result(
            "reply_rollback_history_response_invalid",
            delete_accepted=True,
        )
    if chat_id != expected_chat_id or session_id != expected_session_id:
        return _result(
            "reply_rollback_history_identity_mismatch",
            delete_accepted=True,
        )

    messages = history.get("message")
    if not isinstance(messages, Mapping):
        return _result(
            "reply_rollback_history_response_invalid",
            delete_accepted=True,
        )
    try:
        message_ids: set[int] = set()
        for raw_key, raw_message in messages.items():
            key_id = _positive_int(raw_key)
            if not isinstance(raw_message, Mapping):
                raise ValueError("invalid message")
            item_id = _positive_int(raw_message.get("id"))
            if item_id != key_id or item_id in message_ids:
                raise ValueError("ambiguous message")
            message_ids.add(item_id)
    except ValueError:
        return _result(
            "reply_rollback_history_response_invalid",
            delete_accepted=True,
        )

    if preview.messageId in message_ids:
        return _result(
            "reply_rollback_target_still_present",
            delete_accepted=True,
        )

    return ReplyRollbackFixtureResult(
        status=ReplyRollbackStatus.VERIFIED,
        reason="reply_rollback_fixture_verified",
        fixture_delete_response_accepted=True,
        fixture_target_absent_after_delete=True,
        rollback_contract_locally_tested=True,
    )


__all__ = [
    "BITRIX_REPLY_DELETE_METHOD",
    "ReplyRollbackDeletePreview",
    "ReplyRollbackFixtureResult",
    "ReplyRollbackStatus",
    "build_reply_rollback_delete_preview",
    "reply_delete_response_is_success",
    "verify_reply_rollback_fixture",
]
