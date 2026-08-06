"""Preflight de solo lectura y previews inertes para una Línea Abierta piloto."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bitrix_client import (
    _remote_error_code,
    _retry_after_seconds,
    _validated_portal_url,
)
from .bot_v2_preflight import (
    BotV2RegistrationPreview,
    build_controlled_registration_preview,
)
from .pilot_scope import PilotScopeRule


BITRIX_OPENLINE_DIALOG_GET_PATH = "/rest/imopenlines.dialog.get"
BITRIX_OPENLINE_CONFIG_GET_PATH = "/rest/imopenlines.config.get"
BITRIX_OPENLINE_CONFIG_UPDATE_METHOD = "imopenlines.config.update"
MAX_CONTROLLED_R0_WINDOW = timedelta(minutes=15)
_RETRYABLE_CODES = {
    "QUERY_LIMIT_EXCEEDED",
    "INTERNAL_SERVER_ERROR",
    "ERROR_UNEXPECTED_ANSWER",
    "OVERLOAD_LIMIT",
}


class OpenLineDialog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)
    dialog_id: str = Field(pattern=r"^chat[1-9][0-9]*$")
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)

    @property
    def config_id(self) -> int:
        parts = self.entity_id.split("|")
        if len(parts) < 4 or not parts[0].strip():
            raise ValueError("openline_entity_id_invalid")
        try:
            value = int(parts[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("openline_entity_id_invalid") from exc
        if value <= 0:
            raise ValueError("openline_entity_id_invalid")
        return value


class OpenLineDialogResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    result: OpenLineDialog


class OpenLineConfigSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    config_id: int = Field(alias="ID", gt=0)
    line_name: str = Field(alias="LINE_NAME", min_length=1)
    active: str = Field(alias="ACTIVE", pattern=r"^[YN]$")
    welcome_bot_enable: str = Field(alias="WELCOME_BOT_ENABLE", pattern=r"^[YN]$")
    welcome_bot_join: str = Field(alias="WELCOME_BOT_JOIN", pattern=r"^(first|always)$")
    welcome_bot_id: int = Field(alias="WELCOME_BOT_ID", ge=0)
    welcome_bot_time: int = Field(alias="WELCOME_BOT_TIME", ge=0)
    welcome_bot_left: str = Field(alias="WELCOME_BOT_LEFT", pattern=r"^(queue|close)$")
    no_answer_bot_id: int = Field(alias="NO_ANSWER_BOT_ID", ge=0)
    close_bot_id: int = Field(alias="CLOSE_BOT_ID", ge=0)
    auto_close_bot_id: int = Field(alias="AUTO_CLOSE_BOT_ID", ge=0)
    worktime_dayoff_bot_id: int = Field(alias="WORKTIME_DAYOFF_BOT_ID", ge=0)


class OpenLineConfigResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    result: OpenLineConfigSnapshot


class OpenLineReadDecision(str, Enum):
    SUCCESS = "success"
    RETRY = "retry"
    FAIL = "fail"


@dataclass(frozen=True)
class OpenLineReadResult:
    decision: OpenLineReadDecision
    dialog: Optional[OpenLineDialog] = None
    config: Optional[OpenLineConfigSnapshot] = None
    error_code: Optional[str] = None
    http_status: Optional[int] = None
    retry_after_seconds: int = 0

    def __post_init__(self) -> None:
        if self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds no puede ser negativo")
        if self.decision is OpenLineReadDecision.SUCCESS:
            if (self.dialog is None) == (self.config is None):
                raise ValueError("success requiere exactamente una lectura")
            if self.error_code is not None or self.retry_after_seconds:
                raise ValueError("success no admite error ni reintento")
            return
        if self.dialog is not None or self.config is not None or not self.error_code:
            raise ValueError("retry y fail requieren solo un error seguro")


class BitrixOpenLinePreflightClient:
    """Solo permite leer el diálogo objetivo y su configuración de línea."""

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
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        root = _validated_portal_url(portal_url)
        self._dialog_endpoint = f"{root}{BITRIX_OPENLINE_DIALOG_GET_PATH}"
        self._config_endpoint = f"{root}{BITRIX_OPENLINE_CONFIG_GET_PATH}"
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def get_dialog(self, chat_id: int) -> OpenLineReadResult:
        if chat_id <= 0:
            raise ValueError("chat_id debe ser positivo")
        response = await self._post(self._dialog_endpoint, {"CHAT_ID": chat_id})
        if isinstance(response, OpenLineReadResult):
            return response
        try:
            parsed = OpenLineDialogResponse.model_validate(response.json())
            parsed.result.config_id
        except (ValueError, ValidationError):
            return self._invalid_response(response.status_code)
        return OpenLineReadResult(
            decision=OpenLineReadDecision.SUCCESS,
            dialog=parsed.result,
            http_status=response.status_code,
        )

    async def get_config(self, config_id: int) -> OpenLineReadResult:
        if config_id <= 0:
            raise ValueError("config_id debe ser positivo")
        response = await self._post(
            self._config_endpoint,
            {"CONFIG_ID": config_id, "WITH_QUEUE": "N", "SHOW_OFFLINE": "N"},
        )
        if isinstance(response, OpenLineReadResult):
            return response
        try:
            parsed = OpenLineConfigResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            return self._invalid_response(response.status_code)
        return OpenLineReadResult(
            decision=OpenLineReadDecision.SUCCESS,
            config=parsed.result,
            http_status=response.status_code,
        )

    async def _post(
        self,
        endpoint: str,
        payload: dict[str, object],
    ) -> httpx.Response | OpenLineReadResult:
        try:
            response = await self._http_client.post(
                endpoint,
                json={**payload, "auth": self._access_token},
            )
        except httpx.TimeoutException:
            return self._error(OpenLineReadDecision.RETRY, "openline_preflight_timeout")
        except httpx.TransportError:
            return self._error(
                OpenLineReadDecision.RETRY,
                "openline_preflight_transport_error",
            )
        remote_code = _remote_error_code(response)
        if remote_code == "expired_token":
            return self._error(
                OpenLineReadDecision.RETRY,
                "openline_preflight_token_expired",
                response,
            )
        if (
            response.status_code in {408, 425, 429}
            or 500 <= response.status_code <= 599
            or remote_code in _RETRYABLE_CODES
        ):
            return self._error(
                OpenLineReadDecision.RETRY,
                "openline_preflight_retryable",
                response,
            )
        if remote_code is not None or not 200 <= response.status_code <= 299:
            return self._error(
                OpenLineReadDecision.FAIL,
                "openline_preflight_permanent",
                response,
            )
        return response

    @staticmethod
    def _invalid_response(status: int) -> OpenLineReadResult:
        return OpenLineReadResult(
            decision=OpenLineReadDecision.FAIL,
            error_code="openline_preflight_invalid_response",
            http_status=status,
        )

    @staticmethod
    def _error(
        decision: OpenLineReadDecision,
        code: str,
        response: Optional[httpx.Response] = None,
    ) -> OpenLineReadResult:
        return OpenLineReadResult(
            decision=decision,
            error_code=code,
            http_status=response.status_code if response else None,
            retry_after_seconds=(
                _retry_after_seconds(response)
                if response is not None and decision is OpenLineReadDecision.RETRY
                else 0
            ),
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class OpenLinePreflightStatus(str, Enum):
    READY = "ready"
    RETRY = "retry"
    FAILED = "failed"
    MISMATCH = "mismatch"


class OpenLinePreflightResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: OpenLinePreflightStatus
    reason: str
    chat_id: int = Field(gt=0)
    dialog_id: str
    config: Optional[OpenLineConfigSnapshot] = None


class OpenLinePreflightInspector:
    def __init__(self, client: BitrixOpenLinePreflightClient) -> None:
        self._client = client

    async def inspect(self, *, chat_id: int, dialog_id: str) -> OpenLinePreflightResult:
        expected_dialog = f"chat{chat_id}"
        if chat_id <= 0 or dialog_id != expected_dialog:
            raise ValueError("openline_controlled_identity_invalid")
        dialog_read = await self._client.get_dialog(chat_id)
        if dialog_read.decision is not OpenLineReadDecision.SUCCESS:
            return self._failure(dialog_read, chat_id, dialog_id)
        return await self.inspect_dialog(
            dialog=dialog_read.dialog,
            chat_id=chat_id,
            dialog_id=dialog_id,
        )

    async def inspect_dialog(
        self,
        *,
        dialog: Optional[OpenLineDialog],
        chat_id: int,
        dialog_id: str,
    ) -> OpenLinePreflightResult:
        """Valida un diálogo ya leído y consume sólo config.get."""

        expected_dialog = f"chat{chat_id}"
        if chat_id <= 0 or dialog_id != expected_dialog:
            raise ValueError("openline_controlled_identity_invalid")
        if (
            dialog is None
            or dialog.id != chat_id
            or dialog.dialog_id != dialog_id
            or dialog.entity_type.upper() != "LINES"
        ):
            return OpenLinePreflightResult(
                status=OpenLinePreflightStatus.MISMATCH,
                reason="openline_dialog_identity_mismatch",
                chat_id=chat_id,
                dialog_id=dialog_id,
            )
        config_read = await self._client.get_config(dialog.config_id)
        if config_read.decision is not OpenLineReadDecision.SUCCESS:
            return self._failure(config_read, chat_id, dialog_id)
        config = config_read.config
        if config is None or config.config_id != dialog.config_id:
            return OpenLinePreflightResult(
                status=OpenLinePreflightStatus.MISMATCH,
                reason="openline_config_identity_mismatch",
                chat_id=chat_id,
                dialog_id=dialog_id,
            )
        if config.active != "Y":
            return OpenLinePreflightResult(
                status=OpenLinePreflightStatus.MISMATCH,
                reason="openline_config_inactive",
                chat_id=chat_id,
                dialog_id=dialog_id,
                config=config,
            )
        return OpenLinePreflightResult(
            status=OpenLinePreflightStatus.READY,
            reason="openline_snapshot_ready",
            chat_id=chat_id,
            dialog_id=dialog_id,
            config=config,
        )

    @staticmethod
    def _failure(
        read: OpenLineReadResult,
        chat_id: int,
        dialog_id: str,
    ) -> OpenLinePreflightResult:
        return OpenLinePreflightResult(
            status=(
                OpenLinePreflightStatus.RETRY
                if read.decision is OpenLineReadDecision.RETRY
                else OpenLinePreflightStatus.FAILED
            ),
            reason=read.error_code or "openline_preflight_failed",
            chat_id=chat_id,
            dialog_id=dialog_id,
        )


class WelcomeBotParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    WELCOME_BOT_ENABLE: str = Field(pattern=r"^[YN]$")
    WELCOME_BOT_JOIN: str = Field(pattern=r"^(first|always)$")
    WELCOME_BOT_ID: int = Field(ge=0)
    WELCOME_BOT_TIME: int = Field(ge=0)
    WELCOME_BOT_LEFT: str = Field(pattern=r"^(queue|close)$")


class OpenLineUpdatePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    CONFIG_ID: int = Field(gt=0)
    PARAMS: WelcomeBotParams


class OpenLineUpdatePreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    executable: bool = False
    payload: OpenLineUpdatePayload


class ControlledPilotPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registration: BotV2RegistrationPreview
    link: OpenLineUpdatePreview
    rollback: OpenLineUpdatePreview
    allowlist: PilotScopeRule
    impact_scope: str = "open_line_global"
    requires_special_attention: bool = True
    warning: str = "linking_is_not_limited_to_the_controlled_chat"


def build_controlled_pilot_preview(
    *,
    preflight: OpenLinePreflightResult,
    bot_id: int,
    member_id: str,
    webhook_url: str,
    valid_from: datetime,
    valid_until: datetime,
) -> ControlledPilotPreview:
    if preflight.status is not OpenLinePreflightStatus.READY or preflight.config is None:
        raise ValueError("openline_snapshot_not_ready")
    if bot_id <= 0 or bot_id == preflight.config.welcome_bot_id:
        raise ValueError("openline_new_bot_id_invalid")
    member = member_id.strip()
    if not member:
        raise ValueError("openline_member_id_invalid")
    original = preflight.config
    link_params = WelcomeBotParams(
        WELCOME_BOT_ENABLE="Y",
        WELCOME_BOT_JOIN=original.welcome_bot_join,
        WELCOME_BOT_ID=bot_id,
        WELCOME_BOT_TIME=original.welcome_bot_time,
        WELCOME_BOT_LEFT=original.welcome_bot_left,
    )
    rollback_params = WelcomeBotParams(
        WELCOME_BOT_ENABLE=original.welcome_bot_enable,
        WELCOME_BOT_JOIN=original.welcome_bot_join,
        WELCOME_BOT_ID=original.welcome_bot_id,
        WELCOME_BOT_TIME=original.welcome_bot_time,
        WELCOME_BOT_LEFT=original.welcome_bot_left,
    )
    allowlist = PilotScopeRule(
        member_id=member,
        bot_id=bot_id,
        dialog_id=preflight.dialog_id,
        chat_id=preflight.chat_id,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    if (
        allowlist.valid_from is None
        or allowlist.valid_until is None
        or allowlist.valid_until - allowlist.valid_from > MAX_CONTROLLED_R0_WINDOW
    ):
        raise ValueError("openline_pilot_window_invalid")
    return ControlledPilotPreview(
        registration=build_controlled_registration_preview(webhook_url),
        link=OpenLineUpdatePreview(
            method=BITRIX_OPENLINE_CONFIG_UPDATE_METHOD,
            executable=False,
            payload=OpenLineUpdatePayload(
                CONFIG_ID=original.config_id,
                PARAMS=link_params,
            ),
        ),
        rollback=OpenLineUpdatePreview(
            method=BITRIX_OPENLINE_CONFIG_UPDATE_METHOD,
            executable=False,
            payload=OpenLineUpdatePayload(
                CONFIG_ID=original.config_id,
                PARAMS=rollback_params,
            ),
        ),
        allowlist=allowlist,
    )
