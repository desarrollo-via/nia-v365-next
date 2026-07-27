"""Composición opcional y fail-closed del puente efímero R0."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Optional

from fastapi import APIRouter

from .config import ConnectorMode, ConnectorSettings
from .openline_r0_bridge import (
    InMemoryR0ReceiptBridge,
    R0_BRIDGE_PREFIX,
    build_r0_receipt_bridge_router,
)
from .review_auth import SingleReviewerAuthenticator
from .webhook_handler import WebhookReceiptObserver


class R0BridgeMountConfigurationError(RuntimeError):
    """Impide iniciar G0 cuando se solicita un puente ambiguo o inseguro."""


R0_BRIDGE_EMBEDDED_PREFIX = "/internal/r0-receipts"


@dataclass(frozen=True)
class R0BridgeMount:
    enabled: bool
    router: Optional[APIRouter] = None
    receipt_observer: Optional[WebhookReceiptObserver] = None


def build_optional_r0_bridge_mount(
    settings: ConnectorSettings,
    *,
    prefix: str = R0_BRIDGE_PREFIX,
    bridge_factory: Callable[[], InMemoryR0ReceiptBridge] = (
        InMemoryR0ReceiptBridge
    ),
) -> R0BridgeMount:
    """Construye una única sesión en memoria solo bajo configuración exacta."""

    if not settings.r0_bridge_configuration_valid:
        raise R0BridgeMountConfigurationError(
            "r0_bridge_switch_invalid"
        )
    if not settings.r0_bridge_enabled:
        return R0BridgeMount(enabled=False)
    if (
        settings.requested_mode != ConnectorMode.OFF.value
        or settings.effective_mode is not ConnectorMode.OFF
        or not settings.activation_locked
        or settings.external_calls_enabled
        or settings.pilot_enabled
        or not settings.pilot_emergency_stop
        or not settings.pilot_configuration_valid
    ):
        raise R0BridgeMountConfigurationError(
            "r0_bridge_safety_state_invalid"
        )

    authenticator = SingleReviewerAuthenticator(
        review_token=settings.review_token,
        actor=settings.review_actor,
        credential_id=settings.review_credential_id,
    )
    if not authenticator.configured:
        raise R0BridgeMountConfigurationError(
            "r0_bridge_review_auth_missing"
        )

    bridge = bridge_factory()
    return R0BridgeMount(
        enabled=True,
        router=build_r0_receipt_bridge_router(
            bridge,
            authenticator,
            prefix=prefix,
        ),
        receipt_observer=bridge.observe,
    )


__all__ = [
    "R0BridgeMount",
    "R0BridgeMountConfigurationError",
    "R0_BRIDGE_EMBEDDED_PREFIX",
    "build_optional_r0_bridge_mount",
]
