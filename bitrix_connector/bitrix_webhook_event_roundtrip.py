"""Adapta un evento webhook v2 exacto al recorrido M59 con rollback."""

from __future__ import annotations

from typing import Optional

from .bitrix_history_r0_isolated_roundtrip import (
    InjectedBitrixSender,
    InjectedNiaSender,
)
from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_reply_rollback_adapter import (
    InjectedPostDeleteHistoryReader,
    InjectedReplyDeleter,
)
from .bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
    InjectedPostSendHistoryReader,
    run_composed_roundtrip_with_rollback,
)
from .bitrix_history_r0_runner import (
    CONTROLLED_CHAT_ID,
    CONTROLLED_DIALOG_ID,
    BitrixHistoryR0Status,
)
from .models import NormalizedBitrixEvent
from .openline_link_rehearsal import CONTROLLED_BOT_ID


def _canonical_event_payload(
    event: NormalizedBitrixEvent,
    *,
    session_id: int,
) -> object:
    if (
        not isinstance(event, NormalizedBitrixEvent)
        or event.event != "ONIMBOTV2MESSAGEADD"
        or event.bot_id != CONTROLLED_BOT_ID
        or event.chat_id != CONTROLLED_CHAT_ID
        or event.dialog_id != CONTROLLED_DIALOG_ID
        or event.message_id <= 1
        or event.author_id <= 0
        or event.user_id != event.author_id
        or event.user_is_bot
        or not event.user_is_connector
        or event.is_system
        or not event.text.strip()
        or session_id <= 0
    ):
        raise ValueError("webhook_event_scope_invalid")
    return {
        "result": {
            "chatId": CONTROLLED_CHAT_ID,
            "sessionId": session_id,
            "message": [
                {
                    "id": event.message_id,
                    "chatid": CONTROLLED_CHAT_ID,
                    "senderid": event.author_id,
                    "recipientid": CONTROLLED_DIALOG_ID,
                    "date": str(event.timestamp or "event"),
                    "text": event.text,
                }
            ],
            "users": [{"id": event.author_id, "connector": True}],
        }
    }


async def run_exact_controlled_webhook_event_roundtrip_with_rollback(
    *,
    plan: ProtectedRealRoundtripPlan,
    preflight: BitrixHistoryR0PreflightOutcome,
    event: NormalizedBitrixEvent,
    nia_sender: InjectedNiaSender,
    bitrix_sender: InjectedBitrixSender,
    post_send_history_reader: InjectedPostSendHistoryReader,
    deleter: InjectedReplyDeleter,
    post_delete_history_reader: InjectedPostDeleteHistoryReader,
    emergency_rollback: bool = False,
) -> ComposedRoundtripResult:
    """Procesa sólo el evento que coincide con el ancla fresca posterior."""

    result = preflight.result
    if (
        result.status is not BitrixHistoryR0Status.READY
        or result.reason != "bitrix_history_preflight_ready"
        or result.dialog_read_calls != 1
        or result.history_read_calls != 0
        or not result.dialog_verified
        or not result.session_verified
        or not result.baseline_captured
        or not result.resources_closed
        or preflight.identity_diagnostic is not None
        or not preflight.anchor_available
    ):
        raise ValueError("webhook_event_preflight_invalid")
    anchor = preflight.require_anchor()
    if anchor.baseline_last_message_id != event.message_id:
        raise ValueError("webhook_event_anchor_mismatch")
    payload = _canonical_event_payload(event, session_id=anchor.session_id)
    try:
        return await run_composed_roundtrip_with_rollback(
            plan=plan,
            payload=payload,
            expected_chat_id=CONTROLLED_CHAT_ID,
            expected_dialog_id=CONTROLLED_DIALOG_ID,
            expected_session_id=anchor.session_id,
            baseline_message_id=event.message_id - 1,
            controlled_bot_id=CONTROLLED_BOT_ID,
            nia_sender=nia_sender,
            bitrix_sender=bitrix_sender,
            post_send_history_reader=post_send_history_reader,
            deleter=deleter,
            post_delete_history_reader=post_delete_history_reader,
            expected_sender_id=event.author_id,
            emergency_rollback=emergency_rollback,
        )
    finally:
        payload = None


__all__ = [
    "run_exact_controlled_webhook_event_roundtrip_with_rollback",
]
