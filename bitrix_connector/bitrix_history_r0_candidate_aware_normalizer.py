"""Normalizador puro M54 de payloads históricos consciente del candidato."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bitrix_history_r0_client import (
    BitrixHistoryMessage,
    BitrixHistoryUser,
    BitrixSessionHistory,
)


_MISSING = object()


class CandidateAwareNormalizationStatus(str, Enum):
    NORMALIZED = "NORMALIZED"
    NO_GO = "NO-GO"


class CandidateAwareNormalizationResult(BaseModel):
    """Salida pública redactada; el historial normalizado permanece privado."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M54"] = "M54"
    status: CandidateAwareNormalizationStatus
    reason: Literal[
        "bitrix_history_payload_normalized",
        "bitrix_history_payload_invalid",
    ]
    failure_category: Optional[
        Literal[
            "reader_history_envelope_invalid",
            "reader_history_collections_invalid",
            "reader_history_fields_invalid",
        ]
    ] = None
    input_message_count: int = Field(ge=0)
    normalized_message_count: int = Field(ge=0)
    ignored_non_candidate_count: int = Field(ge=0)
    history: Optional[BitrixSessionHistory] = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    fixture_only: Literal[True] = True
    real_form_identified: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class _EnvelopeInvalid(ValueError):
    pass


class _CollectionsInvalid(ValueError):
    pass


class _FieldsInvalid(ValueError):
    pass


def _field(
    source: Mapping[str, object],
    aliases: tuple[str, ...],
    *,
    required: bool = True,
) -> object:
    present = [name for name in aliases if name in source]
    if len(present) > 1:
        raise _FieldsInvalid("ambiguous aliases")
    if not present:
        if required:
            raise _FieldsInvalid("missing field")
        return _MISSING
    return source[present[0]]


def _positive_int(value: object) -> int:
    if isinstance(value, bool):
        raise _FieldsInvalid("boolean id")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise _FieldsInvalid("invalid id") from exc
    if normalized <= 0 or str(normalized) != str(value).strip():
        raise _FieldsInvalid("invalid positive id")
    return normalized


def _strict_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if value in ("0", "N", "n", "false", "FALSE"):
        return False
    if value in ("1", "Y", "y", "true", "TRUE"):
        return True
    raise _FieldsInvalid("invalid boolean")


def _collection(value: object) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return list(value)
    if not isinstance(value, Mapping):
        raise _CollectionsInvalid("collection is neither sequence nor map")
    indexed: dict[int, object] = {}
    for raw_key, item in value.items():
        if isinstance(raw_key, bool):
            raise _CollectionsInvalid("boolean collection index")
        try:
            key = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise _CollectionsInvalid("non numeric collection index") from exc
        if key < 0 or str(key) != str(raw_key).strip() or key in indexed:
            raise _CollectionsInvalid("invalid collection index")
        indexed[key] = item
    if sorted(indexed) != list(range(len(indexed))):
        raise _CollectionsInvalid("non dense collection")
    return [indexed[index] for index in range(len(indexed))]


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _FieldsInvalid("entry is not an object")
    return value


def _normalize_user(raw: object) -> BitrixHistoryUser:
    source = _mapping(raw)
    user_id = _positive_int(_field(source, ("id", "ID")))
    connector_value = _field(
        source,
        ("connector", "CONNECTOR", "isConnector"),
        required=False,
    )
    connector = (
        False if connector_value is _MISSING else _strict_bool(connector_value)
    )
    return BitrixHistoryUser(id=user_id, connector=connector)


def _normalize_human_message(raw: Mapping[str, object]) -> BitrixHistoryMessage:
    params = _field(raw, ("params", "PARAMS"), required=False)
    normalized = {
        "id": _positive_int(_field(raw, ("id", "ID"))),
        "chatid": _positive_int(_field(raw, ("chatid", "chatId", "chat_id"))),
        "senderid": _positive_int(
            _field(raw, ("senderid", "senderId", "sender_id"))
        ),
        "recipientid": _field(
            raw,
            ("recipientid", "recipientId", "recipient_id"),
        ),
        "date": _field(raw, ("date", "DATE")),
        "text": _field(raw, ("text", "TEXT")),
        "params": {} if params is _MISSING else params,
    }
    try:
        return BitrixHistoryMessage.model_validate(normalized)
    except ValidationError as exc:
        raise _FieldsInvalid("invalid human message") from exc


def _invalid(
    category: Literal[
        "reader_history_envelope_invalid",
        "reader_history_collections_invalid",
        "reader_history_fields_invalid",
    ],
) -> CandidateAwareNormalizationResult:
    return CandidateAwareNormalizationResult(
        status=CandidateAwareNormalizationStatus.NO_GO,
        reason="bitrix_history_payload_invalid",
        failure_category=category,
        input_message_count=0,
        normalized_message_count=0,
        ignored_non_candidate_count=0,
    )


def normalize_candidate_aware_history_payload(
    *,
    payload: object,
    expected_chat_id: int,
    expected_dialog_id: str,
    expected_session_id: int,
    baseline_message_id: int,
    expected_sender_id: Optional[int] = None,
) -> CandidateAwareNormalizationResult:
    """Normaliza variantes explícitas sin inferir datos de entradas ambiguas."""

    if (
        expected_chat_id <= 0
        or expected_dialog_id != f"chat{expected_chat_id}"
        or expected_session_id <= 0
        or baseline_message_id <= 0
        or (expected_sender_id is not None and expected_sender_id <= 0)
    ):
        raise ValueError("bitrix_history_normalizer_contract_invalid")

    try:
        if not isinstance(payload, Mapping):
            raise _EnvelopeInvalid("root is not an object")
        root = payload
        result_names = [name for name in ("result", "RESULT") if name in root]
        if len(result_names) != 1:
            raise _EnvelopeInvalid("result envelope is missing or ambiguous")
        result = root[result_names[0]]
        if not isinstance(result, Mapping):
            raise _EnvelopeInvalid("result is not an object")
        chat_id = _positive_int(_field(result, ("chatId", "chat_id", "CHAT_ID")))
        session_id = _positive_int(
            _field(result, ("sessionId", "session_id", "SESSION_ID"))
        )
        if chat_id != expected_chat_id or session_id != expected_session_id:
            raise _FieldsInvalid("history identity mismatch")
        raw_messages = _collection(_field(result, ("message", "messages", "MESSAGE")))
        raw_users = _collection(_field(result, ("users", "USERS")))
    except _EnvelopeInvalid:
        return _invalid("reader_history_envelope_invalid")
    except _CollectionsInvalid:
        return _invalid("reader_history_collections_invalid")
    except _FieldsInvalid:
        return _invalid("reader_history_fields_invalid")

    try:
        users = tuple(_normalize_user(raw) for raw in raw_users)
        if len({user.id for user in users}) != len(users):
            raise _FieldsInvalid("duplicate user id")
        users_by_id = {user.id: user for user in users}
        normalized_messages: list[BitrixHistoryMessage] = []
        ignored = 0
        for raw_message in raw_messages:
            source = _mapping(raw_message)
            sender_id = _positive_int(
                _field(source, ("senderid", "senderId", "sender_id"))
            )
            author = users_by_id.get(sender_id)
            if author is None:
                raise _FieldsInvalid("unknown sender")
            if not author.connector or (
                expected_sender_id is not None
                and sender_id != expected_sender_id
            ):
                ignored += 1
                continue
            normalized_messages.append(_normalize_human_message(source))
        history = BitrixSessionHistory.model_validate(
            {
                "chatId": chat_id,
                "sessionId": session_id,
                "message": normalized_messages,
                "users": users,
            }
        )
    except (ValidationError, _FieldsInvalid):
        return _invalid("reader_history_fields_invalid")

    return CandidateAwareNormalizationResult(
        status=CandidateAwareNormalizationStatus.NORMALIZED,
        reason="bitrix_history_payload_normalized",
        input_message_count=len(raw_messages),
        normalized_message_count=len(normalized_messages),
        ignored_non_candidate_count=ignored,
        history=history,
    )


__all__ = [
    "CandidateAwareNormalizationResult",
    "CandidateAwareNormalizationStatus",
    "normalize_candidate_aware_history_payload",
]
