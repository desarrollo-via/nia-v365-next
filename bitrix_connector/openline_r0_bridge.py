"""Puente HTTP efímero opt-in para un único recibo R0."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .config import ConnectorSettings
from .models import NormalizedBitrixEvent, WebhookReceipt
from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DIALOG_ID,
)
from .openline_r0_receipt import ControlledR0Receipt, receipt_is_exact
from .pilot_scope import PilotScopeRule
from .review_auth import (
    ReviewAuthenticationOutcome,
    SingleReviewerAuthenticator,
)


R0_BRIDGE_PREFIX = "/bitrix-connector/internal/r0-receipts"
R0_BRIDGE_MAX_WINDOW = timedelta(minutes=10)
RUN_ID_PATTERN = r"^[a-f0-9]{64}$"


class R0BridgeCode(str, Enum):
    ARMED = "armed"
    PENDING = "pending"
    AVAILABLE = "available"
    CONSUMED = "consumed"
    DISARMED = "disarmed"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"


class R0BridgeArmRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(pattern=RUN_ID_PATTERN)
    member_id: str = Field(min_length=1)
    bot_id: int = Field(default=CONTROLLED_BOT_ID)
    chat_id: int = Field(default=CONTROLLED_CHAT_ID)
    dialog_id: str = Field(default=CONTROLLED_DIALOG_ID)
    valid_from: datetime
    valid_until: datetime

    @model_validator(mode="after")
    def validate_exact_scope(self) -> "R0BridgeArmRequest":
        rule = self.to_rule()
        if (
            rule.bot_id != CONTROLLED_BOT_ID
            or rule.chat_id != CONTROLLED_CHAT_ID
            or rule.dialog_id != CONTROLLED_DIALOG_ID
            or rule.valid_from is None
            or rule.valid_until is None
            or rule.valid_until - rule.valid_from > R0_BRIDGE_MAX_WINDOW
        ):
            raise ValueError("r0_bridge_scope_invalid")
        return self

    def to_rule(self) -> PilotScopeRule:
        return PilotScopeRule(
            member_id=self.member_id,
            bot_id=self.bot_id,
            chat_id=self.chat_id,
            dialog_id=self.dialog_id,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )


class R0BridgeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: R0BridgeCode
    receipt: Optional[ControlledR0Receipt] = None


@dataclass
class _ActiveBridgeSession:
    run_id_hash: bytes
    rule: PilotScopeRule
    receipt: Optional[ControlledR0Receipt] = None


def _run_id_hash(run_id: str) -> bytes:
    return hashlib.sha256(run_id.encode("ascii")).digest()


class InMemoryR0ReceiptBridge:
    """Una sesion, un recibo, cero texto y limpieza por consumo o expiracion."""

    def __init__(
        self,
        *,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._session: Optional[_ActiveBridgeSession] = None

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("r0_bridge_clock_invalid")
        return now.astimezone(timezone.utc)

    def _expired(self, session: _ActiveBridgeSession, now: datetime) -> bool:
        return session.rule.valid_until is None or now >= session.rule.valid_until

    def _matches_run(self, session: _ActiveBridgeSession, run_id: str) -> bool:
        try:
            candidate = _run_id_hash(run_id)
        except (UnicodeEncodeError, AttributeError):
            return False
        return hmac.compare_digest(candidate, session.run_id_hash)

    async def arm(self, request: R0BridgeArmRequest) -> R0BridgeResponse:
        rule = request.to_rule()
        now = self._now()
        if not rule.active_at(now):
            return R0BridgeResponse(code=R0BridgeCode.EXPIRED)
        async with self._lock:
            if self._session is not None and self._expired(self._session, now):
                self._session = None
            if self._session is not None:
                return R0BridgeResponse(code=R0BridgeCode.CONFLICT)
            self._session = _ActiveBridgeSession(
                run_id_hash=_run_id_hash(request.run_id),
                rule=rule,
            )
        return R0BridgeResponse(code=R0BridgeCode.ARMED)

    async def inspect(self, run_id: str) -> R0BridgeResponse:
        now = self._now()
        async with self._lock:
            session = self._session
            if session is None or not self._matches_run(session, run_id):
                return R0BridgeResponse(code=R0BridgeCode.NOT_FOUND)
            if self._expired(session, now):
                self._session = None
                return R0BridgeResponse(code=R0BridgeCode.EXPIRED)
            return R0BridgeResponse(
                code=(
                    R0BridgeCode.AVAILABLE
                    if session.receipt is not None
                    else R0BridgeCode.PENDING
                )
            )

    async def consume(self, run_id: str) -> R0BridgeResponse:
        now = self._now()
        async with self._lock:
            session = self._session
            if session is None or not self._matches_run(session, run_id):
                return R0BridgeResponse(code=R0BridgeCode.NOT_FOUND)
            if self._expired(session, now):
                self._session = None
                return R0BridgeResponse(code=R0BridgeCode.EXPIRED)
            if session.receipt is None:
                return R0BridgeResponse(code=R0BridgeCode.PENDING)
            receipt = session.receipt
            self._session = None
            return R0BridgeResponse(
                code=R0BridgeCode.CONSUMED,
                receipt=receipt,
            )

    async def disarm(self, run_id: str) -> R0BridgeResponse:
        async with self._lock:
            session = self._session
            if session is None or not self._matches_run(session, run_id):
                return R0BridgeResponse(code=R0BridgeCode.NOT_FOUND)
            self._session = None
            return R0BridgeResponse(code=R0BridgeCode.DISARMED)

    async def observe(
        self,
        event: NormalizedBitrixEvent,
        receipt: WebhookReceipt,
        settings: ConnectorSettings,
    ) -> None:
        now = self._now()
        async with self._lock:
            session = self._session
            if session is None or session.receipt is not None:
                return
            if self._expired(session, now):
                self._session = None
                return
            if event.event != "ONIMBOTV2MESSAGEADD":
                return
            if (
                receipt.status != "disabled"
                or receipt.reason != "connector_locked_off"
            ):
                return
            candidate = ControlledR0Receipt(
                event_key=receipt.event_key,
                member_id=event.member_id,
                bot_id=event.bot_id,
                chat_id=event.chat_id,
                dialog_id=event.dialog_id,
                effective_mode=receipt.effective_mode,
                activation_locked=settings.activation_locked,
                external_calls_enabled=settings.external_calls_enabled,
                identity_verified=receipt.identity_verified,
                persisted=receipt.persisted,
                nia_called=receipt.nia_called,
                bitrix_written=receipt.bitrix_written,
            )
            if receipt_is_exact(candidate, session.rule):
                session.receipt = candidate


def build_r0_receipt_bridge_router(
    bridge: InMemoryR0ReceiptBridge,
    authenticator: SingleReviewerAuthenticator,
    *,
    prefix: str = R0_BRIDGE_PREFIX,
) -> APIRouter:
    """Crea el router aislado; la función no lo monta por sí misma."""

    router = APIRouter(prefix=prefix, tags=["bitrix-r0-receipt-target"])

    def response(
        result: R0BridgeResponse,
        *,
        status_code: int = 200,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=result.model_dump(mode="json", exclude_none=True),
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def authenticate(request: Request) -> Optional[JSONResponse]:
        result = authenticator.authenticate(
            request.headers.get("authorization", "")
        )
        if result.accepted:
            return None
        unavailable = (
            result.outcome is ReviewAuthenticationOutcome.UNAVAILABLE
        )
        return JSONResponse(
            status_code=503 if unavailable else 401,
            content={"code": result.reason},
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post("/arm")
    async def arm(request: Request) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        try:
            payload = R0BridgeArmRequest.model_validate(await request.json())
        except (TypeError, ValueError, ValidationError):
            return JSONResponse(
                status_code=422,
                content={"code": "r0_bridge_payload_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        result = await bridge.arm(payload)
        return response(
            result,
            status_code={
                R0BridgeCode.ARMED: 201,
                R0BridgeCode.CONFLICT: 409,
                R0BridgeCode.EXPIRED: 410,
            }.get(result.code, 409),
        )

    @router.get("/{run_id}")
    async def inspect(request: Request, run_id: str) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        result = await bridge.inspect(run_id)
        return response(
            result,
            status_code=404 if result.code is R0BridgeCode.NOT_FOUND else 200,
        )

    @router.post("/{run_id}/consume")
    async def consume(request: Request, run_id: str) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        result = await bridge.consume(run_id)
        return response(
            result,
            status_code=404 if result.code is R0BridgeCode.NOT_FOUND else 200,
        )

    @router.delete("/{run_id}")
    async def disarm(request: Request, run_id: str) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        result = await bridge.disarm(run_id)
        return response(
            result,
            status_code=404 if result.code is R0BridgeCode.NOT_FOUND else 200,
        )

    return router


__all__ = [
    "InMemoryR0ReceiptBridge",
    "R0BridgeArmRequest",
    "R0BridgeCode",
    "R0BridgeResponse",
    "R0_BRIDGE_PREFIX",
    "build_r0_receipt_bridge_router",
]
