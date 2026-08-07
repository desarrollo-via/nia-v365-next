"""Recorrido aislado M55: historial fixture -> NIA doble -> Bitrix doble."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_client import BitrixClientDecision, BitrixClientResult
from .bitrix_history_r0_candidate_aware_normalizer import (
    CandidateAwareNormalizationStatus,
    normalize_candidate_aware_history_payload,
)
from .nia_client import NiaClientDecision, NiaClientResult
from .output_review import (
    MAX_BITRIX_MESSAGE_CHARS,
    BitrixMessageFieldsPreview,
    BitrixMessagePayloadPreview,
)
from .preflight import NiaTextPayloadPreview


class InjectedNiaSender(Protocol):
    async def send_approved_text(
        self,
        payload: NiaTextPayloadPreview,
    ) -> NiaClientResult: ...


class InjectedBitrixSender(Protocol):
    async def send_approved_message(
        self,
        payload: BitrixMessagePayloadPreview,
    ) -> BitrixClientResult: ...


class IsolatedRoundtripStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"


class IsolatedRoundtripResult(BaseModel):
    """Evidencia pública sin texto, respuestas, payloads ni identidades."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M55"] = "M55"
    status: IsolatedRoundtripStatus
    reason: Literal[
        "isolated_roundtrip_verified",
        "isolated_history_invalid",
        "isolated_human_candidate_count_invalid",
        "isolated_nia_failed",
        "isolated_nia_response_invalid",
        "isolated_bitrix_reply_failed",
        "isolated_roundtrip_failed",
    ]
    failure_category: Optional[
        Literal[
            "reader_history_envelope_invalid",
            "reader_history_collections_invalid",
            "reader_history_fields_invalid",
        ]
    ] = None
    candidate_count: int = Field(ge=0)
    nia_call_count: int = Field(ge=0, le=1)
    bitrix_reply_call_count: int = Field(ge=0, le=1)
    fixture_nia_received: bool = False
    fixture_bitrix_reply_sent: bool = False
    same_controlled_dialog_preserved: bool = False
    minimum_filter_only: Literal[True] = True
    exact_text_filter_required: Literal[False] = False
    fixture_only: Literal[True] = True
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def _result(
    reason: str,
    *,
    candidate_count: int = 0,
    nia_call_count: int = 0,
    bitrix_reply_call_count: int = 0,
    failure_category: Optional[str] = None,
) -> IsolatedRoundtripResult:
    return IsolatedRoundtripResult(
        status=IsolatedRoundtripStatus.NO_GO,
        reason=reason,
        failure_category=failure_category,
        candidate_count=candidate_count,
        nia_call_count=nia_call_count,
        bitrix_reply_call_count=bitrix_reply_call_count,
    )


async def run_isolated_history_nia_bitrix_roundtrip(
    *,
    payload: object,
    expected_chat_id: int,
    expected_dialog_id: str,
    expected_session_id: int,
    baseline_message_id: int,
    controlled_bot_id: int,
    nia_sender: InjectedNiaSender,
    bitrix_sender: InjectedBitrixSender,
    expected_sender_id: Optional[int] = None,
) -> IsolatedRoundtripResult:
    """Prueba continuidad mínima con dependencias obligatoriamente inyectadas."""

    if nia_sender is None or bitrix_sender is None or controlled_bot_id <= 0:
        raise ValueError("isolated_roundtrip_contract_invalid")

    normalized = normalize_candidate_aware_history_payload(
        payload=payload,
        expected_chat_id=expected_chat_id,
        expected_dialog_id=expected_dialog_id,
        expected_session_id=expected_session_id,
        expected_sender_id=expected_sender_id,
        baseline_message_id=baseline_message_id,
    )
    if normalized.status is not CandidateAwareNormalizationStatus.NORMALIZED:
        return _result(
            "isolated_history_invalid",
            failure_category=normalized.failure_category,
        )
    history = normalized.history
    if history is None:
        return _result("isolated_history_invalid")

    users = {user.id: user for user in history.users}
    candidates = tuple(
        message
        for message in history.messages
        if message.id > baseline_message_id
        and message.chatid == expected_chat_id
        and message.recipientid == expected_dialog_id
        and users.get(message.senderid) is not None
        and users[message.senderid].connector
        and (
            expected_sender_id is None
            or message.senderid == expected_sender_id
        )
        and bool(message.text.strip())
    )
    if len(candidates) != 1:
        return _result(
            "isolated_human_candidate_count_invalid",
            candidate_count=len(candidates),
        )

    nia_calls = 0
    bitrix_calls = 0
    try:
        message = candidates[0]
        nia_calls = 1
        nia_result = await nia_sender.send_approved_text(
            NiaTextPayloadPreview(
                session_id=f"bitrix:{expected_session_id}:{expected_dialog_id}",
                mensaje=message.text,
            )
        )
        if (
            not isinstance(nia_result, NiaClientResult)
            or nia_result.decision is not NiaClientDecision.SUCCESS
            or nia_result.response is None
        ):
            return _result(
                "isolated_nia_failed",
                candidate_count=1,
                nia_call_count=nia_calls,
            )
        response_text = nia_result.response.respuesta
        if not response_text.strip() or len(response_text) > MAX_BITRIX_MESSAGE_CHARS:
            return _result(
                "isolated_nia_response_invalid",
                candidate_count=1,
                nia_call_count=nia_calls,
            )

        bitrix_calls = 1
        bitrix_result = await bitrix_sender.send_approved_message(
            BitrixMessagePayloadPreview(
                botId=controlled_bot_id,
                dialogId=expected_dialog_id,
                fields=BitrixMessageFieldsPreview(message=response_text),
            )
        )
        if (
            not isinstance(bitrix_result, BitrixClientResult)
            or bitrix_result.decision is not BitrixClientDecision.SUCCESS
        ):
            return _result(
                "isolated_bitrix_reply_failed",
                candidate_count=1,
                nia_call_count=nia_calls,
                bitrix_reply_call_count=bitrix_calls,
            )
    except Exception:
        return _result(
            "isolated_roundtrip_failed",
            candidate_count=1,
            nia_call_count=nia_calls,
            bitrix_reply_call_count=bitrix_calls,
        )

    return IsolatedRoundtripResult(
        status=IsolatedRoundtripStatus.VERIFIED,
        reason="isolated_roundtrip_verified",
        candidate_count=1,
        nia_call_count=1,
        bitrix_reply_call_count=1,
        fixture_nia_received=True,
        fixture_bitrix_reply_sent=True,
        same_controlled_dialog_preserved=True,
    )


__all__ = [
    "InjectedBitrixSender",
    "InjectedNiaSender",
    "IsolatedRoundtripResult",
    "IsolatedRoundtripStatus",
    "run_isolated_history_nia_bitrix_roundtrip",
]
