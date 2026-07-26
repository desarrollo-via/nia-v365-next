"""Política fail-closed para cualquier llamada externa del conector."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .config import ConnectorMode, ConnectorSettings, load_settings


class ExternalAction(str, Enum):
    NIA = "nia"
    BITRIX = "bitrix"


@dataclass(frozen=True)
class ExternalCallDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class ExternalCallPolicy:
    """Evalúa el modo inmediatamente antes de una llamada externa."""

    effective_mode: ConnectorMode
    activation_locked: bool
    external_calls_enabled: bool

    @classmethod
    def from_settings(cls, settings: ConnectorSettings) -> "ExternalCallPolicy":
        return cls(
            effective_mode=settings.effective_mode,
            activation_locked=settings.activation_locked,
            external_calls_enabled=settings.external_calls_enabled,
        )

    def authorize(self, action: ExternalAction) -> ExternalCallDecision:
        if self.activation_locked:
            return ExternalCallDecision(False, "connector_activation_locked")
        if self.effective_mode is ConnectorMode.OFF:
            return ExternalCallDecision(False, "connector_mode_off")
        if not self.external_calls_enabled:
            return ExternalCallDecision(False, "connector_external_calls_disabled")

        if action is ExternalAction.NIA:
            return ExternalCallDecision(True, "nia_call_allowed")
        if self.effective_mode is ConnectorMode.SHADOW:
            return ExternalCallDecision(False, "connector_shadow_blocks_bitrix")
        return ExternalCallDecision(True, "bitrix_call_allowed")


ExternalCallPolicyProvider = Callable[[], ExternalCallPolicy]


def current_external_call_policy() -> ExternalCallPolicy:
    """Relee el entorno en cada barrera; no conserva una activación obsoleta."""

    return ExternalCallPolicy.from_settings(load_settings())
