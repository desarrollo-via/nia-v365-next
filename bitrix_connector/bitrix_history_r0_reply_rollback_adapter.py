"""Adaptador M58 real-ready sólo mediante dependencias inyectadas."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_reply_rollback_contract import (
    ReplyRollbackDeletePreview,
    ReplyRollbackStatus,
    build_reply_rollback_delete_preview,
    reply_delete_response_is_success,
    verify_reply_rollback_fixture,
)


class InjectedReplyDeleter(Protocol):
    async def delete_approved_reply(
        self,
        preview: ReplyRollbackDeletePreview,
    ) -> object: ...


class InjectedPostDeleteHistoryReader(Protocol):
    async def read_post_delete_history(
        self,
        *,
        session_id: int,
    ) -> object: ...


class InjectedReplyRollbackStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"


class InjectedReplyRollbackResult(BaseModel):
    """Salida redactada; nunca conserva payloads, IDs o respuestas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M58"] = "M58"
    status: InjectedReplyRollbackStatus
    reason: Literal[
        "injected_reply_rollback_verified",
        "injected_reply_delete_failed",
        "injected_reply_delete_response_invalid",
        "injected_reply_history_read_failed",
        "injected_reply_rollback_verification_failed",
    ]
    verification_failure_reason: Optional[
        Literal[
            "reply_rollback_history_response_invalid",
            "reply_rollback_history_identity_mismatch",
            "reply_rollback_target_still_present",
        ]
    ] = None
    delete_call_count: int = Field(ge=0, le=1)
    history_read_call_count: int = Field(ge=0, le=1)
    fixture_delete_accepted: bool = False
    fixture_absence_verified: bool = False
    exact_send_receipt_id_used: bool = False
    complete_deletion_required: Literal[True] = True
    same_session_verification_required: Literal[True] = True
    no_retry: Literal[True] = True
    dependencies_injected: Literal[True] = True
    real_ready_contract: Literal[True] = True
    m56_blocked_plan_applied: Literal[True] = True
    fixture_only: Literal[True] = True
    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    source_bound: Literal[False] = False
    authorization_present: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    real_rollback_executed: Literal[False] = False
    real_portal_behavior_verified: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def _no_go(
    reason: str,
    *,
    delete_calls: int,
    history_calls: int,
    verification_reason: Optional[str] = None,
) -> InjectedReplyRollbackResult:
    return InjectedReplyRollbackResult(
        status=InjectedReplyRollbackStatus.NO_GO,
        reason=reason,
        verification_failure_reason=verification_reason,
        delete_call_count=delete_calls,
        history_read_call_count=history_calls,
        exact_send_receipt_id_used=delete_calls == 1,
    )


async def run_injected_reply_rollback(
    *,
    plan: ProtectedRealRoundtripPlan,
    controlled_bot_id: int,
    sent_message_id: int,
    expected_chat_id: int,
    expected_session_id: int,
    deleter: InjectedReplyDeleter,
    history_reader: InjectedPostDeleteHistoryReader,
) -> InjectedReplyRollbackResult:
    """Ejercita máximo un borrado y una relectura, sólo con inyección."""

    if (
        controlled_bot_id <= 0
        or sent_message_id <= 0
        or expected_chat_id <= 0
        or expected_session_id <= 0
        or deleter is None
        or history_reader is None
        or not isinstance(plan, ProtectedRealRoundtripPlan)
        or plan.target_dialog_id != f"chat{expected_chat_id}"
        or plan.controlled_bot_id != controlled_bot_id
        or plan.bitrix_reply_send_budget != 1
        or plan.post_send_history_read_budget != 1
        or not plan.execution_blocked_until_rollback_verified
        or plan.real_execution_authorized
    ):
        raise ValueError("injected_reply_rollback_contract_invalid")

    preview = build_reply_rollback_delete_preview(
        bot_id=controlled_bot_id,
        sent_message_id=sent_message_id,
    )
    try:
        delete_response = await deleter.delete_approved_reply(preview)
    except Exception:
        return _no_go(
            "injected_reply_delete_failed",
            delete_calls=1,
            history_calls=0,
        )
    if not reply_delete_response_is_success(delete_response):
        return _no_go(
            "injected_reply_delete_response_invalid",
            delete_calls=1,
            history_calls=0,
        )

    try:
        history_response = await history_reader.read_post_delete_history(
            session_id=expected_session_id,
        )
    except Exception:
        return _no_go(
            "injected_reply_history_read_failed",
            delete_calls=1,
            history_calls=1,
        )

    verified = verify_reply_rollback_fixture(
        preview=preview,
        delete_response=delete_response,
        post_delete_history_response=history_response,
        expected_chat_id=expected_chat_id,
        expected_session_id=expected_session_id,
    )
    if verified.status is not ReplyRollbackStatus.VERIFIED:
        return _no_go(
            "injected_reply_rollback_verification_failed",
            delete_calls=1,
            history_calls=1,
            verification_reason=verified.reason,
        )

    return InjectedReplyRollbackResult(
        status=InjectedReplyRollbackStatus.VERIFIED,
        reason="injected_reply_rollback_verified",
        delete_call_count=1,
        history_read_call_count=1,
        fixture_delete_accepted=True,
        fixture_absence_verified=True,
        exact_send_receipt_id_used=True,
    )


__all__ = [
    "InjectedPostDeleteHistoryReader",
    "InjectedReplyDeleter",
    "InjectedReplyRollbackResult",
    "InjectedReplyRollbackStatus",
    "run_injected_reply_rollback",
]
