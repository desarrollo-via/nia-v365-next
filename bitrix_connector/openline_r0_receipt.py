"""Compuerta efimera y acotada para demostrar la recepcion real de R0."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .config import ConnectorSettings
from .models import NormalizedBitrixEvent, WebhookReceipt
from .pilot_scope import PilotScopeRule


MAX_R0_RECEIPT_WAIT_SECONDS = 300.0


class ControlledR0Receipt(BaseModel):
    """Evidencia allowlisted sin texto, secretos ni cuerpo del evento."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    member_id: str = Field(min_length=1)
    bot_id: int = Field(gt=0)
    chat_id: int = Field(gt=0)
    dialog_id: str = Field(min_length=1)
    effective_mode: str
    activation_locked: bool
    external_calls_enabled: bool
    identity_verified: bool
    persisted: bool
    nia_called: bool
    bitrix_written: bool


class R0ReceiptGate(Protocol):
    async def arm(self, rule: PilotScopeRule) -> None: ...

    async def wait(self) -> ControlledR0Receipt: ...

    async def close(self) -> None: ...


class ControlledR0ReceiptGate:
    """Conserva como maximo un recibo exacto y descarta el resto."""

    def __init__(
        self,
        *,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._clock = clock
        self._rule: Optional[PilotScopeRule] = None
        self._future: Optional[asyncio.Future[ControlledR0Receipt]] = None
        self._closed = False

    async def arm(self, rule: PilotScopeRule) -> None:
        if self._closed or self._rule is not None:
            raise RuntimeError("r0_receipt_gate_not_armable")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None or not rule.active_at(now):
            raise RuntimeError("r0_receipt_gate_window_invalid")
        self._rule = rule
        self._future = asyncio.get_running_loop().create_future()

    async def observe(
        self,
        event: NormalizedBitrixEvent,
        receipt: WebhookReceipt,
        settings: ConnectorSettings,
    ) -> None:
        """Acepta solo el primer evento exacto que termino inerte en ``off``."""

        if self._closed or self._rule is None or self._future is None:
            return
        if self._future.done() or not self._rule.active_at(self._clock()):
            return
        if event.event != "ONIMBOTV2MESSAGEADD":
            return
        if not self._rule.matches_identity(event):
            return
        if (
            settings.effective_mode.value != "off"
            or not settings.activation_locked
            or settings.external_calls_enabled
            or receipt.status != "disabled"
            or receipt.reason != "connector_locked_off"
            or not receipt.identity_verified
            or receipt.persisted
            or receipt.nia_called
            or receipt.bitrix_written
        ):
            return
        self._future.set_result(
            ControlledR0Receipt(
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
        )

    async def wait(self) -> ControlledR0Receipt:
        if self._closed or self._future is None:
            raise RuntimeError("r0_receipt_gate_not_armed")
        return await asyncio.shield(self._future)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._future is not None and not self._future.done():
            self._future.cancel()


def receipt_is_exact(
    receipt: ControlledR0Receipt,
    rule: PilotScopeRule,
) -> bool:
    return bool(
        receipt.member_id == rule.member_id
        and receipt.bot_id == rule.bot_id
        and receipt.chat_id == rule.chat_id
        and receipt.dialog_id == rule.dialog_id
        and receipt.effective_mode == "off"
        and receipt.activation_locked
        and not receipt.external_calls_enabled
        and receipt.identity_verified
        and not receipt.persisted
        and not receipt.nia_called
        and not receipt.bitrix_written
    )


__all__ = [
    "ControlledR0Receipt",
    "ControlledR0ReceiptGate",
    "MAX_R0_RECEIPT_WAIT_SECONDS",
    "R0ReceiptGate",
    "receipt_is_exact",
]
