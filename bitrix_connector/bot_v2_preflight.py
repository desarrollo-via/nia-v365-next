"""Preflight de lectura y contrato no ejecutable para el bot Open Lines v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ipaddress import ip_address
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bitrix_client import (
    _remote_error_code,
    _retry_after_seconds,
    _validated_portal_url,
)


BITRIX_V2_REVISION_PATH = "/rest/imbot.v2.Revision.get"
BITRIX_V2_BOT_LIST_PATH = "/rest/imbot.v2.Bot.list"
BITRIX_V2_BOT_REGISTER_METHOD = "imbot.v2.Bot.register"
CONTROLLED_BOT_CODE = "nia_next_openline_controlled"
_RETRYABLE_CODES = {
    "QUERY_LIMIT_EXCEEDED",
    "INTERNAL_SERVER_ERROR",
    "ERROR_UNEXPECTED_ANSWER",
    "OVERLOAD_LIMIT",
}


class BotV2Revision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    rest: int = Field(ge=0)
    web: int = Field(ge=0)
    mobile: int = Field(ge=0)
    desktop: int = Field(ge=0)


class BotV2RevisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    result: BotV2Revision


class BotV2Summary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)
    code: str = Field(min_length=1)
    type: str = Field(min_length=1)
    isSupportOpenline: bool = False
    eventMode: str = Field(min_length=1)


class BotV2ListResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    bots: tuple[BotV2Summary, ...] = ()
    hasNextPage: bool = False


class BotV2ListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    result: BotV2ListResult


class BotV2PreflightDecision(str, Enum):
    SUCCESS = "success"
    RETRY = "retry"
    FAIL = "fail"


@dataclass(frozen=True)
class BotV2PreflightCallResult:
    decision: BotV2PreflightDecision
    revision: Optional[BotV2Revision] = None
    bots: tuple[BotV2Summary, ...] = ()
    has_next_page: bool = False
    error_code: Optional[str] = None
    http_status: Optional[int] = None
    retry_after_seconds: int = 0

    def __post_init__(self) -> None:
        if self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds no puede ser negativo")
        if self.decision is BotV2PreflightDecision.SUCCESS:
            if self.error_code is not None or self.retry_after_seconds:
                raise ValueError("success no admite error ni reintento")
            return
        if self.revision is not None or self.bots or not self.error_code:
            raise ValueError("retry y fail requieren solo un error seguro")


class BitrixBotV2PreflightClient:
    """Expone únicamente las dos lecturas requeridas por G1."""

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
        self._revision_endpoint = f"{root}{BITRIX_V2_REVISION_PATH}"
        self._list_endpoint = f"{root}{BITRIX_V2_BOT_LIST_PATH}"
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    async def get_revision(self) -> BotV2PreflightCallResult:
        response = await self._post(self._revision_endpoint, {})
        if isinstance(response, BotV2PreflightCallResult):
            return response
        try:
            parsed = BotV2RevisionResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            return self._invalid_response(response.status_code)
        return BotV2PreflightCallResult(
            decision=BotV2PreflightDecision.SUCCESS,
            revision=parsed.result,
            http_status=response.status_code,
        )

    async def list_bots(self) -> BotV2PreflightCallResult:
        response = await self._post(
            self._list_endpoint,
            {"filter": {"type": "openline"}, "limit": 50, "offset": 0},
        )
        if isinstance(response, BotV2PreflightCallResult):
            return response
        try:
            parsed = BotV2ListResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            return self._invalid_response(response.status_code)
        return BotV2PreflightCallResult(
            decision=BotV2PreflightDecision.SUCCESS,
            bots=parsed.result.bots,
            has_next_page=parsed.result.hasNextPage,
            http_status=response.status_code,
        )

    async def _post(
        self,
        endpoint: str,
        payload: dict[str, object],
    ) -> httpx.Response | BotV2PreflightCallResult:
        request_json = {**payload, "auth": self._access_token}
        try:
            response = await self._http_client.post(endpoint, json=request_json)
        except httpx.TimeoutException:
            return self._error(
                BotV2PreflightDecision.RETRY,
                "bot_v2_preflight_timeout",
            )
        except httpx.TransportError:
            return self._error(
                BotV2PreflightDecision.RETRY,
                "bot_v2_preflight_transport_error",
            )

        remote_code = _remote_error_code(response)
        if remote_code == "expired_token":
            return self._error(
                BotV2PreflightDecision.RETRY,
                "bot_v2_preflight_token_expired",
                response=response,
            )
        if (
            response.status_code == 429
            or 500 <= response.status_code <= 599
            or remote_code in _RETRYABLE_CODES
        ):
            return self._error(
                BotV2PreflightDecision.RETRY,
                "bot_v2_preflight_retryable",
                response=response,
            )
        if remote_code is not None or not 200 <= response.status_code <= 299:
            return self._error(
                BotV2PreflightDecision.FAIL,
                "bot_v2_preflight_permanent",
                response=response,
            )
        return response

    @staticmethod
    def _invalid_response(status: int) -> BotV2PreflightCallResult:
        return BotV2PreflightCallResult(
            decision=BotV2PreflightDecision.FAIL,
            error_code="bot_v2_preflight_invalid_response",
            http_status=status,
        )

    @staticmethod
    def _error(
        decision: BotV2PreflightDecision,
        code: str,
        *,
        response: Optional[httpx.Response] = None,
    ) -> BotV2PreflightCallResult:
        return BotV2PreflightCallResult(
            decision=decision,
            error_code=code,
            http_status=response.status_code if response else None,
            retry_after_seconds=(
                _retry_after_seconds(response)
                if response is not None
                and decision is BotV2PreflightDecision.RETRY
                else 0
            ),
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class BotV2PreflightStatus(str, Enum):
    READY = "ready"
    EXISTING_COMPATIBLE = "existing_compatible"
    EXISTING_CONFLICT = "existing_conflict"
    PAGINATION_REQUIRED = "pagination_required"
    RETRY = "retry"
    FAILED = "failed"


class BotV2PreflightResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: BotV2PreflightStatus
    reason: str
    rest_revision: Optional[int] = Field(default=None, ge=0)
    existing_bot_id: Optional[int] = Field(default=None, gt=0)
    registration_needed: bool = False


class BotV2PreflightInspector:
    def __init__(self, client: BitrixBotV2PreflightClient) -> None:
        self._client = client

    async def inspect(self) -> BotV2PreflightResult:
        revision = await self._client.get_revision()
        if revision.decision is not BotV2PreflightDecision.SUCCESS:
            return self._failure(revision)
        bots = await self._client.list_bots()
        if bots.decision is not BotV2PreflightDecision.SUCCESS:
            return self._failure(bots)
        if bots.has_next_page:
            return BotV2PreflightResult(
                status=BotV2PreflightStatus.PAGINATION_REQUIRED,
                reason="bot_v2_preflight_requires_full_bot_list",
                rest_revision=revision.revision.rest if revision.revision else None,
            )
        existing = next(
            (bot for bot in bots.bots if bot.code == CONTROLLED_BOT_CODE),
            None,
        )
        rest_revision = revision.revision.rest if revision.revision else None
        if existing is None:
            return BotV2PreflightResult(
                status=BotV2PreflightStatus.READY,
                reason="bot_v2_preflight_no_existing_bot",
                rest_revision=rest_revision,
                registration_needed=True,
            )
        compatible = (
            existing.type == "openline"
            and existing.isSupportOpenline
            and existing.eventMode == "webhook"
        )
        return BotV2PreflightResult(
            status=(
                BotV2PreflightStatus.EXISTING_COMPATIBLE
                if compatible
                else BotV2PreflightStatus.EXISTING_CONFLICT
            ),
            reason=(
                "bot_v2_preflight_existing_compatible"
                if compatible
                else "bot_v2_preflight_existing_conflict"
            ),
            rest_revision=rest_revision,
            existing_bot_id=existing.id,
            registration_needed=False,
        )

    @staticmethod
    def _failure(call: BotV2PreflightCallResult) -> BotV2PreflightResult:
        retry = call.decision is BotV2PreflightDecision.RETRY
        return BotV2PreflightResult(
            status=(
                BotV2PreflightStatus.RETRY
                if retry
                else BotV2PreflightStatus.FAILED
            ),
            reason=call.error_code or "bot_v2_preflight_failed",
        )


class BotV2RegistrationFields(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    properties: dict[str, str]
    type: str
    isSupportOpenline: bool
    eventMode: str
    webhookUrl: str
    isHidden: bool
    isReactionsEnabled: bool


class BotV2RegistrationPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    executable: bool = False
    fields: BotV2RegistrationFields


def build_controlled_registration_preview(
    webhook_url: str,
) -> BotV2RegistrationPreview:
    cleaned = webhook_url.strip()
    parsed = httpx.URL(cleaned)
    host = (parsed.host or "").lower()
    try:
        ip_address(host)
        host_is_ip = True
    except ValueError:
        host_is_ip = False
    if (
        parsed.scheme != "https"
        or not host
        or parsed.userinfo
        or parsed.query
        or parsed.fragment
        or parsed.path != "/bitrix-connector/webhook"
        or host in {"localhost", "127.0.0.1", "::1"}
        or host.endswith(".trycloudflare.com")
        or host_is_ip
    ):
        raise ValueError("bot_v2_stable_webhook_url_invalid")
    return BotV2RegistrationPreview(
        method=BITRIX_V2_BOT_REGISTER_METHOD,
        executable=False,
        fields=BotV2RegistrationFields(
            code=CONTROLLED_BOT_CODE,
            properties={
                "name": "NIA Next Controlado",
                "workPosition": "Piloto supervisado",
            },
            type="openline",
            isSupportOpenline=True,
            eventMode="webhook",
            webhookUrl=cleaned,
            isHidden=True,
            isReactionsEnabled=False,
        ),
    )
