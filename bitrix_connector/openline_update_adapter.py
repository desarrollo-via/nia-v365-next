"""Adaptador one-shot verificable para actualizar los cinco campos del bot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .bitrix_client import _remote_error_code, _validated_portal_url
from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    CONTROLLED_CONFIG_ID,
    ORIGINAL_WELCOME_BOT_ID,
)
from .openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_UPDATE_METHOD,
    BitrixOpenLinePreflightClient,
    OpenLineReadDecision,
    OpenLineUpdatePreview,
)


BITRIX_OPENLINE_CONFIG_UPDATE_PATH = "/rest/imopenlines.config.update"
_UNCERTAIN_CODES = {
    "QUERY_LIMIT_EXCEEDED",
    "INTERNAL_SERVER_ERROR",
    "ERROR_UNEXPECTED_ANSWER",
    "OVERLOAD_LIMIT",
}


class _UpdateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    result: bool


class OpenLineUpdateDecision(str, Enum):
    SUCCESS = "success"
    UNCERTAIN = "uncertain"
    FAIL = "fail"


@dataclass(frozen=True)
class OpenLineUpdateCallResult:
    decision: OpenLineUpdateDecision
    error_code: Optional[str] = None
    http_status: Optional[int] = None

    def __post_init__(self) -> None:
        if self.decision is OpenLineUpdateDecision.SUCCESS:
            if self.error_code is not None:
                raise ValueError("success no admite error")
            return
        if not self.error_code:
            raise ValueError("uncertain y fail requieren error seguro")


class BitrixOpenLineUpdateClient:
    """Expone una unica mutacion fija; no posee lectura, CLI ni reintentos."""

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
        self._endpoint = f"{root}{BITRIX_OPENLINE_CONFIG_UPDATE_PATH}"
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    async def update(
        self,
        preview: OpenLineUpdatePreview,
    ) -> OpenLineUpdateCallResult:
        _validate_update_preview(preview)
        payload = preview.payload.model_dump(mode="json")
        payload["auth"] = self._access_token
        try:
            response = await self._http_client.post(
                self._endpoint,
                json=payload,
            )
        except httpx.TimeoutException:
            return self._uncertain("openline_update_timeout")
        except httpx.TransportError:
            return self._uncertain("openline_update_transport_error")

        status = response.status_code
        remote_code = _remote_error_code(response)
        if (
            status in {408, 425, 429}
            or 500 <= status <= 599
            or remote_code in _UNCERTAIN_CODES
        ):
            return self._uncertain(
                "openline_update_remote_uncertain",
                status=status,
            )
        if remote_code is not None or not 200 <= status <= 299:
            return self._failed(
                "openline_update_rejected",
                status=status,
            )
        try:
            parsed = _UpdateResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            return self._uncertain(
                "openline_update_invalid_response",
                status=status,
            )
        if not parsed.result:
            return self._failed(
                "openline_update_config_not_found",
                status=status,
            )
        return OpenLineUpdateCallResult(
            decision=OpenLineUpdateDecision.SUCCESS,
            http_status=status,
        )

    @staticmethod
    def _uncertain(
        code: str,
        *,
        status: Optional[int] = None,
    ) -> OpenLineUpdateCallResult:
        return OpenLineUpdateCallResult(
            decision=OpenLineUpdateDecision.UNCERTAIN,
            error_code=code,
            http_status=status,
        )

    @staticmethod
    def _failed(
        code: str,
        *,
        status: Optional[int] = None,
    ) -> OpenLineUpdateCallResult:
        return OpenLineUpdateCallResult(
            decision=OpenLineUpdateDecision.FAIL,
            error_code=code,
            http_status=status,
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class VerifiedUpdateStatus(str, Enum):
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"
    FAILED = "failed"
    CONFLICT = "conflict"
    ALREADY_USED = "already_used"


class VerifiedUpdateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: VerifiedUpdateStatus
    reason: str
    expected_bot_id: int
    update_attempted: bool
    config_read_attempted: bool
    verified: bool


class OneShotVerifiedOpenLineUpdate:
    """Consume una instancia por actualizacion y la verifica con config.get."""

    def __init__(
        self,
        update_client: BitrixOpenLineUpdateClient,
        read_client: BitrixOpenLinePreflightClient,
    ) -> None:
        self._update_client = update_client
        self._read_client = read_client
        self._used = False

    async def apply(
        self,
        preview: OpenLineUpdatePreview,
    ) -> VerifiedUpdateResult:
        expected_bot_id = preview.payload.PARAMS.WELCOME_BOT_ID
        if self._used:
            return self._result(
                VerifiedUpdateStatus.ALREADY_USED,
                "openline_update_adapter_already_used",
                expected_bot_id,
            )
        self._used = True
        call = await self._update_client.update(preview)
        if call.decision is OpenLineUpdateDecision.UNCERTAIN:
            return self._result(
                VerifiedUpdateStatus.UNCERTAIN,
                call.error_code or "openline_update_uncertain",
                expected_bot_id,
                update_attempted=True,
            )
        if call.decision is not OpenLineUpdateDecision.SUCCESS:
            return self._result(
                VerifiedUpdateStatus.FAILED,
                call.error_code or "openline_update_failed",
                expected_bot_id,
                update_attempted=True,
            )

        read = await self._read_client.get_config(CONTROLLED_CONFIG_ID)
        if read.decision is not OpenLineReadDecision.SUCCESS or read.config is None:
            return self._result(
                VerifiedUpdateStatus.UNCERTAIN,
                "openline_update_verification_unavailable",
                expected_bot_id,
                update_attempted=True,
                config_read_attempted=True,
            )
        params = preview.payload.PARAMS
        config = read.config
        verified = (
            config.config_id == CONTROLLED_CONFIG_ID
            and config.welcome_bot_enable == params.WELCOME_BOT_ENABLE
            and config.welcome_bot_join == params.WELCOME_BOT_JOIN
            and config.welcome_bot_id == params.WELCOME_BOT_ID
            and config.welcome_bot_time == params.WELCOME_BOT_TIME
            and config.welcome_bot_left == params.WELCOME_BOT_LEFT
        )
        if not verified:
            return self._result(
                VerifiedUpdateStatus.CONFLICT,
                "openline_update_verification_conflict",
                expected_bot_id,
                update_attempted=True,
                config_read_attempted=True,
            )
        return self._result(
            VerifiedUpdateStatus.VERIFIED,
            "openline_update_verified",
            expected_bot_id,
            update_attempted=True,
            config_read_attempted=True,
            verified=True,
        )

    @staticmethod
    def _result(
        status: VerifiedUpdateStatus,
        reason: str,
        expected_bot_id: int,
        *,
        update_attempted: bool = False,
        config_read_attempted: bool = False,
        verified: bool = False,
    ) -> VerifiedUpdateResult:
        return VerifiedUpdateResult(
            status=status,
            reason=reason,
            expected_bot_id=expected_bot_id,
            update_attempted=update_attempted,
            config_read_attempted=config_read_attempted,
            verified=verified,
        )


def _validate_update_preview(preview: OpenLineUpdatePreview) -> None:
    params = preview.payload.PARAMS
    if (
        preview.method != BITRIX_OPENLINE_CONFIG_UPDATE_METHOD
        or preview.executable
        or preview.payload.CONFIG_ID != CONTROLLED_CONFIG_ID
        or params.WELCOME_BOT_ENABLE != "Y"
        or params.WELCOME_BOT_JOIN != "always"
        or params.WELCOME_BOT_ID
        not in {CONTROLLED_BOT_ID, ORIGINAL_WELCOME_BOT_ID}
        or params.WELCOME_BOT_TIME != 0
        or params.WELCOME_BOT_LEFT != "close"
    ):
        raise ValueError("openline_update_preview_not_controlled")
