"""Composición M62 de alcance exacto para el único diálogo controlado."""

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
from .openline_link_rehearsal import CONTROLLED_BOT_ID


def _require_controlled_preflight(
    preflight: BitrixHistoryR0PreflightOutcome,
):
    if not isinstance(preflight, BitrixHistoryR0PreflightOutcome):
        raise ValueError("exact_scope_preflight_invalid")
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
        raise ValueError("exact_scope_preflight_invalid")
    return preflight.require_anchor()


async def run_exact_controlled_roundtrip_with_rollback(
    *,
    plan: ProtectedRealRoundtripPlan,
    preflight: BitrixHistoryR0PreflightOutcome,
    payload: object,
    nia_sender: InjectedNiaSender,
    bitrix_sender: InjectedBitrixSender,
    post_send_history_reader: InjectedPostSendHistoryReader,
    deleter: InjectedReplyDeleter,
    post_delete_history_reader: InjectedPostDeleteHistoryReader,
    expected_sender_id: Optional[int] = None,
    emergency_rollback: bool = False,
) -> ComposedRoundtripResult:
    """Deriva la sesión del preflight y no admite identidades configurables."""

    anchor = _require_controlled_preflight(preflight)
    return await run_composed_roundtrip_with_rollback(
        plan=plan,
        payload=payload,
        expected_chat_id=CONTROLLED_CHAT_ID,
        expected_dialog_id=CONTROLLED_DIALOG_ID,
        expected_session_id=anchor.session_id,
        baseline_message_id=anchor.baseline_last_message_id,
        controlled_bot_id=CONTROLLED_BOT_ID,
        expected_sender_id=expected_sender_id,
        nia_sender=nia_sender,
        bitrix_sender=bitrix_sender,
        post_send_history_reader=post_send_history_reader,
        deleter=deleter,
        post_delete_history_reader=post_delete_history_reader,
        emergency_rollback=emergency_rollback,
    )


__all__ = ["run_exact_controlled_roundtrip_with_rollback"]
