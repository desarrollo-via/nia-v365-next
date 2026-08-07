"""Composición M59 fixture-only del recorrido M55 y el rollback M58."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Mapping, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_client import BitrixClientDecision, BitrixClientResult
from .bitrix_history_r0_isolated_roundtrip import (
    InjectedBitrixSender,
    InjectedNiaSender,
    IsolatedRoundtripStatus,
    run_isolated_history_nia_bitrix_roundtrip,
)
from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_reply_rollback_adapter import (
    InjectedPostDeleteHistoryReader,
    InjectedReplyDeleter,
    InjectedReplyRollbackStatus,
    run_injected_reply_rollback,
)
from .output_review import BitrixMessagePayloadPreview


class InjectedPostSendHistoryReader(Protocol):
    async def read_post_send_history(self, *, session_id: int) -> object: ...


class ComposedRoundtripStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ROLLED_BACK = "ROLLED-BACK"
    NO_GO = "NO-GO"


class ComposedRoundtripResult(BaseModel):
    """Evidencia pública redactada sin textos, payloads, respuestas ni IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M59"] = "M59"
    status: ComposedRoundtripStatus
    reason: Literal[
        "composed_roundtrip_verified_and_preserved",
        "composed_sealed_rollback_safety_verified",
        "composed_roundtrip_stopped_before_receipt",
        "composed_post_send_verification_failed_rollback_verified",
        "composed_emergency_rollback_verified",
        "composed_required_rollback_failed",
    ]
    roundtrip_call_count: Literal[1] = 1
    post_send_history_read_count: int = Field(ge=0, le=1)
    rollback_call_count: int = Field(ge=0, le=1)
    delete_call_count: int = Field(ge=0, le=1)
    post_delete_history_read_count: int = Field(ge=0, le=1)
    exact_send_receipt_obtained: bool = False
    exact_send_receipt_used_for_verification: bool = False
    exact_send_receipt_used_for_rollback: bool = False
    fixture_reply_present_same_session: bool = False
    fixture_reply_preserved: bool = False
    fixture_rollback_verified: bool = False
    emergency_rollback_requested: bool = False
    rollback_required_after_receipt_failure: bool = False
    no_retry: Literal[True] = True
    dependencies_injected: Literal[True] = True
    binding_class: Literal[
        "fixture-double", "sealed-in-memory-concrete"
    ] = "fixture-double"
    fixture_only: bool = True
    concrete_clients_constructed_in_memory: bool = False
    network_capable_resources_accepted: Literal[False] = False
    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    source_bound: Literal[False] = False
    authorization_present: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    real_roundtrip_executed: Literal[False] = False
    real_rollback_executed: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class _ReceiptRecordingSender:
    def __init__(self, sender: InjectedBitrixSender) -> None:
        self._sender = sender
        self.sent_message_id: Optional[int] = None

    async def send_approved_message(
        self,
        payload: BitrixMessagePayloadPreview,
    ) -> BitrixClientResult:
        result = await self._sender.send_approved_message(payload)
        if (
            isinstance(result, BitrixClientResult)
            and result.decision is BitrixClientDecision.SUCCESS
            and result.response is not None
        ):
            self.sent_message_id = result.response.result.id
        return result


def _positive_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean id")
    normalized = int(value)
    if normalized <= 0 or str(normalized) != str(value).strip():
        raise ValueError("invalid id")
    return normalized


def _exact_reply_is_present(
    response: object,
    *,
    sent_message_id: int,
    expected_chat_id: int,
    expected_session_id: int,
) -> bool:
    if not isinstance(response, Mapping):
        return False
    history = response.get("result")
    if not isinstance(history, Mapping):
        return False
    try:
        if (
            _positive_int(history.get("chatId")) != expected_chat_id
            or _positive_int(history.get("sessionId")) != expected_session_id
        ):
            return False
        messages = history.get("message")
        if not isinstance(messages, Mapping):
            return False
        ids: set[int] = set()
        for raw_key, raw_message in messages.items():
            key_id = _positive_int(raw_key)
            if not isinstance(raw_message, Mapping):
                return False
            item_id = _positive_int(raw_message.get("id"))
            if key_id != item_id or item_id in ids:
                return False
            ids.add(item_id)
    except (TypeError, ValueError):
        return False
    return sent_message_id in ids


async def run_composed_roundtrip_with_rollback(
    *,
    plan: ProtectedRealRoundtripPlan,
    payload: object,
    expected_chat_id: int,
    expected_dialog_id: str,
    expected_session_id: int,
    baseline_message_id: int,
    controlled_bot_id: int,
    nia_sender: InjectedNiaSender,
    bitrix_sender: InjectedBitrixSender,
    post_send_history_reader: InjectedPostSendHistoryReader,
    deleter: InjectedReplyDeleter,
    post_delete_history_reader: InjectedPostDeleteHistoryReader,
    expected_sender_id: Optional[int] = None,
    emergency_rollback: bool = False,
) -> ComposedRoundtripResult:
    """Conserva éxito verificado; revierte una vez todo fallo posterior al ID."""

    if (
        not isinstance(plan, ProtectedRealRoundtripPlan)
        or plan.target_dialog_id != expected_dialog_id
        or plan.target_dialog_id != f"chat{expected_chat_id}"
        or plan.controlled_bot_id != controlled_bot_id
        or not plan.execution_blocked_until_rollback_verified
        or plan.real_execution_authorized
        or nia_sender is None
        or bitrix_sender is None
        or post_send_history_reader is None
        or deleter is None
        or post_delete_history_reader is None
    ):
        raise ValueError("composed_roundtrip_contract_invalid")

    recording_sender = _ReceiptRecordingSender(bitrix_sender)
    roundtrip = await run_isolated_history_nia_bitrix_roundtrip(
        payload=payload,
        expected_chat_id=expected_chat_id,
        expected_dialog_id=expected_dialog_id,
        expected_session_id=expected_session_id,
        expected_sender_id=expected_sender_id,
        baseline_message_id=baseline_message_id,
        controlled_bot_id=controlled_bot_id,
        nia_sender=nia_sender,
        bitrix_sender=recording_sender,
    )
    sent_message_id = recording_sender.sent_message_id
    if sent_message_id is None:
        return ComposedRoundtripResult(
            status=ComposedRoundtripStatus.NO_GO,
            reason="composed_roundtrip_stopped_before_receipt",
            post_send_history_read_count=0,
            rollback_call_count=0,
            delete_call_count=0,
            post_delete_history_read_count=0,
            emergency_rollback_requested=emergency_rollback,
        )

    reply_verified = False
    post_send_reads = 0
    if roundtrip.status is IsolatedRoundtripStatus.VERIFIED:
        post_send_reads = 1
        try:
            post_send = await post_send_history_reader.read_post_send_history(
                session_id=expected_session_id,
            )
            reply_verified = _exact_reply_is_present(
                post_send,
                sent_message_id=sent_message_id,
                expected_chat_id=expected_chat_id,
                expected_session_id=expected_session_id,
            )
        except Exception:
            reply_verified = False

    if reply_verified and not emergency_rollback:
        return ComposedRoundtripResult(
            status=ComposedRoundtripStatus.VERIFIED,
            reason="composed_roundtrip_verified_and_preserved",
            post_send_history_read_count=1,
            rollback_call_count=0,
            delete_call_count=0,
            post_delete_history_read_count=0,
            exact_send_receipt_obtained=True,
            exact_send_receipt_used_for_verification=True,
            fixture_reply_present_same_session=True,
            fixture_reply_preserved=True,
        )

    rollback = await run_injected_reply_rollback(
        plan=plan,
        controlled_bot_id=controlled_bot_id,
        sent_message_id=sent_message_id,
        expected_chat_id=expected_chat_id,
        expected_session_id=expected_session_id,
        deleter=deleter,
        history_reader=post_delete_history_reader,
    )
    rollback_verified = rollback.status is InjectedReplyRollbackStatus.VERIFIED
    if rollback_verified:
        reason = (
            "composed_emergency_rollback_verified"
            if emergency_rollback
            else "composed_post_send_verification_failed_rollback_verified"
        )
        status = ComposedRoundtripStatus.ROLLED_BACK
    else:
        reason = "composed_required_rollback_failed"
        status = ComposedRoundtripStatus.NO_GO
    return ComposedRoundtripResult(
        status=status,
        reason=reason,
        post_send_history_read_count=post_send_reads,
        rollback_call_count=1,
        delete_call_count=rollback.delete_call_count,
        post_delete_history_read_count=rollback.history_read_call_count,
        exact_send_receipt_obtained=True,
        exact_send_receipt_used_for_verification=post_send_reads == 1,
        exact_send_receipt_used_for_rollback=True,
        fixture_reply_present_same_session=reply_verified,
        fixture_rollback_verified=rollback_verified,
        emergency_rollback_requested=emergency_rollback,
        rollback_required_after_receipt_failure=not emergency_rollback,
    )


__all__ = [
    "ComposedRoundtripResult",
    "ComposedRoundtripStatus",
    "InjectedPostSendHistoryReader",
    "run_composed_roundtrip_with_rollback",
]
