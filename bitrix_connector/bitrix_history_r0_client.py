"""Cliente Bitrix mínimo y de solo lectura para la observación R0 por historial."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bitrix_client import _remote_error_code, _validated_portal_url


BITRIX_DIALOG_GET_PATH = "/rest/imopenlines.dialog.get"
BITRIX_SESSION_HISTORY_GET_PATH = "/rest/imopenlines.session.history.get"
MAX_HISTORY_RESPONSE_BYTES = 2 * 1024 * 1024
_RETRYABLE_CODES = {
    "QUERY_LIMIT_EXCEEDED",
    "INTERNAL_SERVER_ERROR",
    "ERROR_UNEXPECTED_ANSWER",
    "OVERLOAD_LIMIT",
}
_HISTORY_COLLECTION_FIELDS = frozenset({"message", "messages", "users"})


class BitrixHistoryDialog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)
    dialog_id: str = Field(pattern=r"^chat[1-9][0-9]*$")
    entity_type: str = Field(min_length=1)
    entity_id: Optional[str] = None
    entity_data_1: str = Field(min_length=1)
    role: str = Field(min_length=1)
    last_message_id: int = Field(gt=0)

    @property
    def session_id(self) -> int:
        parts = self.entity_data_1.split("|")
        if len(parts) < 6:
            raise ValueError("bitrix_history_session_identity_invalid")
        try:
            session_id = int(parts[5])
        except (TypeError, ValueError) as exc:
            raise ValueError("bitrix_history_session_identity_invalid") from exc
        if session_id <= 0:
            raise ValueError("bitrix_history_session_identity_invalid")
        return session_id


class BitrixHistoryMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)
    chatid: int = Field(gt=0)
    senderid: int = Field(gt=0)
    recipientid: str = Field(min_length=1)
    date: str = Field(min_length=1)
    text: str
    params: dict[str, object] = Field(default_factory=dict)


class BitrixHistoryUser(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)
    connector: bool = False


class BitrixSessionHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    chat_id: int = Field(alias="chatId", gt=0)
    session_id: int = Field(alias="sessionId", gt=0)
    messages: tuple[BitrixHistoryMessage, ...] = Field(alias="message")
    users: tuple[BitrixHistoryUser, ...]


class _DialogResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    result: BitrixHistoryDialog


class _HistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    result: BitrixSessionHistory


def _history_validation_error_code(error: ValidationError) -> str:
    """Clasifica sólo la ubicación estructural, nunca valores del cuerpo."""

    collection_invalid = False
    field_invalid = False
    for issue in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = tuple(issue.get("loc") or ())
        if not location or location[0] != "result" or len(location) == 1:
            return "bitrix_history_invalid_envelope"
        if location[1] in _HISTORY_COLLECTION_FIELDS and len(location) == 2:
            collection_invalid = True
        else:
            field_invalid = True
    if collection_invalid:
        return "bitrix_history_invalid_collections"
    if field_invalid:
        return "bitrix_history_invalid_fields"
    return "bitrix_history_invalid_response"


class BitrixHistoryReadDecision(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"


@dataclass(frozen=True)
class BitrixHistoryReadResult:
    decision: BitrixHistoryReadDecision
    dialog: Optional[BitrixHistoryDialog] = None
    history: Optional[BitrixSessionHistory] = None
    error_code: Optional[str] = None
    http_status: Optional[int] = None

    def __post_init__(self) -> None:
        if self.decision is BitrixHistoryReadDecision.SUCCESS:
            if (self.dialog is None) == (self.history is None):
                raise ValueError("success requiere exactamente una lectura")
            if self.error_code is not None:
                raise ValueError("success no admite error_code")
            return
        if self.dialog is not None or self.history is not None or not self.error_code:
            raise ValueError("fail requiere solo un error_code seguro")


class BitrixHistoryR0Client:
    """Expone únicamente las dos lecturas aprobadas para R0."""

    def __init__(
        self,
        *,
        portal_url: str,
        access_token: str,
        timeout_seconds: float,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        token = access_token.strip()
        if not token:
            raise ValueError("access_token no puede estar vacío")
        if timeout_seconds <= 0 or timeout_seconds > 10:
            raise ValueError("timeout_seconds debe estar entre 0 y 10")
        root = _validated_portal_url(portal_url)
        self._dialog_endpoint = f"{root}{BITRIX_DIALOG_GET_PATH}"
        self._history_endpoint = f"{root}{BITRIX_SESSION_HISTORY_GET_PATH}"
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def get_dialog(self, dialog_id: str) -> BitrixHistoryReadResult:
        chat_id = self._chat_id(dialog_id)
        response = await self._post(self._dialog_endpoint, {"CHAT_ID": chat_id})
        if isinstance(response, BitrixHistoryReadResult):
            return response
        try:
            parsed = _DialogResponse.model_validate(response.json())
            parsed.result.session_id
        except (ValueError, ValidationError):
            return self._invalid_response(response.status_code)
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.SUCCESS,
            dialog=parsed.result,
            http_status=response.status_code,
        )

    async def get_session_history(self, session_id: int) -> BitrixHistoryReadResult:
        if session_id <= 0:
            raise ValueError("session_id debe ser positivo")
        response = await self._post(
            self._history_endpoint,
            {"SESSION_ID": session_id},
        )
        if isinstance(response, BitrixHistoryReadResult):
            return response
        if len(response.content) > MAX_HISTORY_RESPONSE_BYTES:
            return BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.FAIL,
                error_code="bitrix_history_response_too_large",
                http_status=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError:
            return self._failed(
                "bitrix_history_invalid_envelope",
                response.status_code,
            )
        try:
            parsed = _HistoryResponse.model_validate(payload)
        except ValidationError as exc:
            return self._failed(
                _history_validation_error_code(exc),
                response.status_code,
            )
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.SUCCESS,
            history=parsed.result,
            http_status=response.status_code,
        )

    @staticmethod
    def _chat_id(dialog_id: str) -> int:
        if not dialog_id.startswith("chat") or not dialog_id[4:].isdigit():
            raise ValueError("dialog_id debe tener formato chatN")
        chat_id = int(dialog_id[4:])
        if chat_id <= 0:
            raise ValueError("dialog_id debe tener formato chatN")
        return chat_id

    async def _post(
        self,
        endpoint: str,
        payload: dict[str, object],
    ) -> httpx.Response | BitrixHistoryReadResult:
        try:
            response = await self._http_client.post(
                endpoint,
                json={**payload, "auth": self._access_token},
            )
        except httpx.TimeoutException:
            return self._failed("bitrix_history_timeout")
        except httpx.TransportError:
            return self._failed("bitrix_history_transport_error")
        remote_code = _remote_error_code(response)
        if remote_code == "expired_token":
            return self._failed("bitrix_history_token_expired", response.status_code)
        if (
            response.status_code in {408, 425, 429}
            or 500 <= response.status_code <= 599
            or remote_code in _RETRYABLE_CODES
        ):
            return self._failed("bitrix_history_read_unavailable", response.status_code)
        if remote_code is not None or not 200 <= response.status_code <= 299:
            return self._failed("bitrix_history_read_rejected", response.status_code)
        return response

    @staticmethod
    def _invalid_response(status: int) -> BitrixHistoryReadResult:
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.FAIL,
            error_code="bitrix_history_invalid_response",
            http_status=status,
        )

    @staticmethod
    def _failed(code: str, status: Optional[int] = None) -> BitrixHistoryReadResult:
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.FAIL,
            error_code=code,
            http_status=status,
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()
