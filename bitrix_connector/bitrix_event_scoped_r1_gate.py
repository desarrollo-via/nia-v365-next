"""Compuerta one-shot dormida para el recorrido R1 iniciado por webhook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional, Protocol

from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)
from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .bitrix_history_r0_runner import CONTROLLED_CHAT_ID, CONTROLLED_DIALOG_ID
from .config import ConnectorMode, ConnectorSettings
from .models import NormalizedBitrixEvent, WebhookReceipt
from .openline_link_rehearsal import CONTROLLED_BOT_ID


EVENT_R1_FIRST_CONFIRMATION = (
    "PRIMERA CONFIRMACION R1 EVENTO EFIMERO CHAT78733 BOT373259"
)
EVENT_R1_SECOND_CONFIRMATION = (
    "SEGUNDA CONFIRMACION R1 EVENTO EFIMERO EJECUCION INMEDIATA"
)


class EventPreflightOperation(Protocol):
    async def __call__(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
    ) -> BitrixHistoryR0PreflightOutcome: ...


class EventRoundtripOperation(Protocol):
    async def __call__(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
        outcome: BitrixHistoryR0PreflightOutcome,
        event: NormalizedBitrixEvent,
    ) -> object: ...


@dataclass(frozen=True)
class EventScopedR1GateSnapshot:
    phase: Literal["M86-CE"] = "M86-CE"
    state: Literal[
        "DORMANT",
        "AWAITING-MANUAL-REMOVAL",
        "AWAITING-SECOND-CONFIRMATION",
        "ATTENTION-REQUIRED",
        "VERIFIED",
        "ROLLED-BACK",
        "NO-GO",
    ] = "DORMANT"
    first_confirmation_calls: int = 0
    manual_removal_calls: int = 0
    second_confirmation_calls: int = 0
    event_calls: int = 0
    preflight_calls: int = 0
    roundtrip_calls: int = 0
    attention_required_now: bool = False
    human_message_required_now: bool = False
    execution_enabled: bool = False
    exact_chat_bound: Literal[True] = True
    exact_bot_bound: Literal[True] = True
    retry_budget: Literal[0] = 0
    oauth_refresh_calls: Literal[0] = 0
    oauth_persistence_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False


class EventScopedR1Gate:
    """Exige orden humano exacto antes de consumir un único evento válido."""

    def __init__(
        self,
        *,
        preflight: EventPreflightOperation,
        roundtrip: EventRoundtripOperation,
        execution_enabled: bool = False,
    ) -> None:
        if (
            not callable(preflight)
            or not callable(roundtrip)
            or type(execution_enabled) is not bool
        ):
            raise TypeError("event_r1_gate_dependency_invalid")
        self._preflight: Optional[EventPreflightOperation] = preflight
        self._roundtrip: Optional[EventRoundtripOperation] = roundtrip
        self._execution_enabled = execution_enabled
        self._state = "DORMANT"
        self._first_calls = 0
        self._manual_calls = 0
        self._second_calls = 0
        self._event_calls = 0
        self._preflight_calls = 0
        self._roundtrip_calls = 0

    def accept_first_confirmation_once(self, text: str) -> EventScopedR1GateSnapshot:
        self._first_calls += 1
        if (
            self._state != "DORMANT"
            or not self._execution_enabled
            or text != EVENT_R1_FIRST_CONFIRMATION
        ):
            self._state = "NO-GO"
        else:
            self._state = "AWAITING-MANUAL-REMOVAL"
        return self.snapshot()

    def confirm_manual_removal_once(self, *, confirmed: bool) -> EventScopedR1GateSnapshot:
        self._manual_calls += 1
        if self._state != "AWAITING-MANUAL-REMOVAL" or confirmed is not True:
            self._state = "NO-GO"
        else:
            self._state = "AWAITING-SECOND-CONFIRMATION"
        return self.snapshot()

    def accept_second_confirmation_once(self, text: str) -> EventScopedR1GateSnapshot:
        self._second_calls += 1
        if (
            self._state != "AWAITING-SECOND-CONFIRMATION"
            or text != EVENT_R1_SECOND_CONFIRMATION
        ):
            self._state = "NO-GO"
        else:
            self._state = "ATTENTION-REQUIRED"
        return self.snapshot()

    async def observe(
        self,
        event: NormalizedBitrixEvent,
        receipt: WebhookReceipt,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
    ) -> None:
        if self._state != "ATTENTION-REQUIRED":
            return
        self._state = "NO-GO"
        self._event_calls = 1
        if (
            not self._execution_enabled
            or event.event != "ONIMBOTV2MESSAGEADD"
            or event.bot_id != CONTROLLED_BOT_ID
            or event.chat_id != CONTROLLED_CHAT_ID
            or event.dialog_id != CONTROLLED_DIALOG_ID
            or receipt.status != "disabled"
            or receipt.reason != "connector_locked_off"
            or not receipt.identity_verified
            or receipt.persisted
            or receipt.nia_called
            or receipt.bitrix_written
            or settings.effective_mode is not ConnectorMode.OFF
            or not settings.activation_locked
            or settings.external_calls_enabled
            or self._preflight is None
            or self._roundtrip is None
        ):
            return
        preflight, self._preflight = self._preflight, None
        roundtrip, self._roundtrip = self._roundtrip, None
        try:
            self._preflight_calls = 1
            outcome = await preflight(settings, token_view)
            if not isinstance(outcome, BitrixHistoryR0PreflightOutcome):
                return
            self._roundtrip_calls = 1
            result = await roundtrip(settings, token_view, outcome, event)
            result_state = getattr(result, "state", None)
            if result_state not in ("VERIFIED", "ROLLED-BACK"):
                result_state = getattr(getattr(result, "status", None), "value", None)
            self._state = (
                result_state
                if result_state in ("VERIFIED", "ROLLED-BACK")
                else "NO-GO"
            )
        except Exception:
            self._state = "NO-GO"

    def snapshot(self) -> EventScopedR1GateSnapshot:
        attention = self._state == "ATTENTION-REQUIRED"
        return EventScopedR1GateSnapshot(
            state=self._state,
            first_confirmation_calls=self._first_calls,
            manual_removal_calls=self._manual_calls,
            second_confirmation_calls=self._second_calls,
            event_calls=self._event_calls,
            preflight_calls=self._preflight_calls,
            roundtrip_calls=self._roundtrip_calls,
            attention_required_now=attention,
            human_message_required_now=attention,
            execution_enabled=self._execution_enabled,
        )

    def __repr__(self) -> str:
        return "EventScopedR1Gate(<redacted>)"


__all__ = [
    "EVENT_R1_FIRST_CONFIRMATION",
    "EVENT_R1_SECOND_CONFIRMATION",
    "EventScopedR1Gate",
    "EventScopedR1GateSnapshot",
]
