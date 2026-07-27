"""Registro one-shot, acotado e inyectable del bot controlado Bitrix v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bitrix_client import (
    _remote_error_code,
    _retry_after_seconds,
    _validated_portal_url,
)
from .bot_v2_preflight import (
    BITRIX_V2_BOT_REGISTER_METHOD,
    CONTROLLED_BOT_CODE,
    BotV2PreflightResult,
    BotV2PreflightStatus,
    BotV2RegistrationPreview,
    build_controlled_registration_preview,
)


BITRIX_V2_BOT_REGISTER_PATH = "/rest/imbot.v2.Bot.register"
BITRIX_V2_BOT_UNREGISTER_METHOD = "imbot.v2.Bot.unregister"
_RETRYABLE_CODES = {
    "QUERY_LIMIT_EXCEEDED",
    "INTERNAL_SERVER_ERROR",
    "ERROR_UNEXPECTED_ANSWER",
    "OVERLOAD_LIMIT",
}


class RegisteredBot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)
    code: str = Field(min_length=1)
    type: str = Field(min_length=1)
    isSupportOpenline: bool
    eventMode: str = Field(min_length=1)
    isHidden: bool
    isReactionsEnabled: bool


class _RegistrationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    bot: RegisteredBot


class _RegistrationEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    result: _RegistrationResponse


class RegistrationCallDecision(str, Enum):
    SUCCESS = "success"
    RETRY = "retry"
    FAIL = "fail"


@dataclass(frozen=True)
class RegistrationCallResult:
    decision: RegistrationCallDecision
    bot: Optional[RegisteredBot] = None
    error_code: Optional[str] = None
    http_status: Optional[int] = None
    retry_after_seconds: int = 0

    def __post_init__(self) -> None:
        if self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds no puede ser negativo")
        if self.decision is RegistrationCallDecision.SUCCESS:
            if self.bot is None or self.error_code is not None:
                raise ValueError("success requiere bot y no admite error")
            return
        if self.bot is not None or not self.error_code:
            raise ValueError("retry y fail requieren solo un error seguro")


class BitrixBotV2RegistrationClient:
    """Cliente de mutacion con una unica operacion REST fija."""

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
            raise ValueError("access_token no puede estar vacio")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        root = _validated_portal_url(portal_url)
        self._endpoint = f"{root}{BITRIX_V2_BOT_REGISTER_PATH}"
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    async def register(
        self,
        preview: BotV2RegistrationPreview,
    ) -> RegistrationCallResult:
        _validate_controlled_preview(preview)
        payload = {
            "fields": preview.fields.model_dump(mode="json"),
            "auth": self._access_token,
        }
        try:
            response = await self._http_client.post(
                self._endpoint,
                json=payload,
            )
        except httpx.TimeoutException:
            return self._error(
                RegistrationCallDecision.RETRY,
                "bot_v2_registration_timeout",
            )
        except httpx.TransportError:
            return self._error(
                RegistrationCallDecision.RETRY,
                "bot_v2_registration_transport_error",
            )

        remote_code = _remote_error_code(response)
        if remote_code == "expired_token":
            return self._error(
                RegistrationCallDecision.RETRY,
                "bot_v2_registration_token_expired",
                response=response,
            )
        if (
            response.status_code == 429
            or 500 <= response.status_code <= 599
            or remote_code in _RETRYABLE_CODES
        ):
            return self._error(
                RegistrationCallDecision.RETRY,
                "bot_v2_registration_retryable",
                response=response,
            )
        if remote_code is not None or not 200 <= response.status_code <= 299:
            return self._error(
                RegistrationCallDecision.FAIL,
                "bot_v2_registration_permanent",
                response=response,
            )
        try:
            parsed = _RegistrationEnvelope.model_validate(response.json())
        except (ValueError, ValidationError):
            return self._error(
                RegistrationCallDecision.FAIL,
                "bot_v2_registration_invalid_response",
                response=response,
            )
        return RegistrationCallResult(
            decision=RegistrationCallDecision.SUCCESS,
            bot=parsed.result.bot,
            http_status=response.status_code,
        )

    @staticmethod
    def _error(
        decision: RegistrationCallDecision,
        code: str,
        *,
        response: Optional[httpx.Response] = None,
    ) -> RegistrationCallResult:
        return RegistrationCallResult(
            decision=decision,
            error_code=code,
            http_status=response.status_code if response else None,
            retry_after_seconds=(
                _retry_after_seconds(response)
                if response is not None
                and decision is RegistrationCallDecision.RETRY
                else 0
            ),
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class BotV2UnregisterPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["imbot.v2.Bot.unregister"] = BITRIX_V2_BOT_UNREGISTER_METHOD
    executable: Literal[False] = False
    requires_explicit_authorization: Literal[True] = True
    botId: int = Field(gt=0)


class ControlledRegistrationStatus(str, Enum):
    REGISTERED = "registered"
    IDEMPOTENT = "idempotent"
    RETRY = "retry"
    FAILED = "failed"


class ControlledRegistrationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ControlledRegistrationStatus
    reason: str
    bot_id: Optional[int] = Field(default=None, gt=0)
    registration_attempted: bool = False
    unregister_preview: Optional[BotV2UnregisterPreview] = None


class ControlledBotRegistrationRunner:
    """Ejecuta como maximo un registro y falla cerrado en cualquier desvio."""

    def __init__(self, client: BitrixBotV2RegistrationClient) -> None:
        self._client = client

    async def run(
        self,
        *,
        preflight: BotV2PreflightResult,
        preview: BotV2RegistrationPreview,
    ) -> ControlledRegistrationResult:
        _validate_controlled_preview(preview)
        if preflight.status is BotV2PreflightStatus.EXISTING_COMPATIBLE:
            if preflight.existing_bot_id is None:
                return self._failed("bot_v2_registration_missing_existing_id")
            return ControlledRegistrationResult(
                status=ControlledRegistrationStatus.IDEMPOTENT,
                reason="bot_v2_registration_existing_compatible",
                bot_id=preflight.existing_bot_id,
                unregister_preview=_build_unregister_preview(
                    preflight.existing_bot_id
                ),
            )
        if (
            preflight.status is not BotV2PreflightStatus.READY
            or not preflight.registration_needed
            or preflight.existing_bot_id is not None
        ):
            return self._failed("bot_v2_registration_preflight_not_ready")

        call = await self._client.register(preview)
        if call.decision is RegistrationCallDecision.RETRY:
            return ControlledRegistrationResult(
                status=ControlledRegistrationStatus.RETRY,
                reason=call.error_code or "bot_v2_registration_retry",
                registration_attempted=True,
            )
        if call.decision is not RegistrationCallDecision.SUCCESS or call.bot is None:
            return ControlledRegistrationResult(
                status=ControlledRegistrationStatus.FAILED,
                reason=call.error_code or "bot_v2_registration_failed",
                registration_attempted=True,
            )
        if not _bot_matches_preview(call.bot, preview):
            return ControlledRegistrationResult(
                status=ControlledRegistrationStatus.FAILED,
                reason="bot_v2_registration_result_conflict",
                registration_attempted=True,
            )
        return ControlledRegistrationResult(
            status=ControlledRegistrationStatus.REGISTERED,
            reason="bot_v2_registration_created",
            bot_id=call.bot.id,
            registration_attempted=True,
            unregister_preview=_build_unregister_preview(call.bot.id),
        )

    @staticmethod
    def _failed(reason: str) -> ControlledRegistrationResult:
        return ControlledRegistrationResult(
            status=ControlledRegistrationStatus.FAILED,
            reason=reason,
        )


def _validate_controlled_preview(preview: BotV2RegistrationPreview) -> None:
    expected = build_controlled_registration_preview(preview.fields.webhookUrl)
    if (
        preview.method != BITRIX_V2_BOT_REGISTER_METHOD
        or preview.executable
        or preview != expected
    ):
        raise ValueError("bot_v2_registration_preview_not_controlled")


def _bot_matches_preview(
    bot: RegisteredBot,
    preview: BotV2RegistrationPreview,
) -> bool:
    fields = preview.fields
    return (
        bot.code == CONTROLLED_BOT_CODE == fields.code
        and bot.type == fields.type
        and bot.isSupportOpenline is fields.isSupportOpenline
        and bot.eventMode == fields.eventMode
        and bot.isHidden is fields.isHidden
        and bot.isReactionsEnabled is fields.isReactionsEnabled
    )


def _build_unregister_preview(bot_id: int) -> BotV2UnregisterPreview:
    return BotV2UnregisterPreview(botId=bot_id)
