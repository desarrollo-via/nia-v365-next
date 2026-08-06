"""Montaje integrado M86-CF, deliberadamente dormido y no activable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .webhook_handler import ProtectedWebhookOAuthObserver


@dataclass(frozen=True)
class EventScopedR1Mount:
    phase: Literal["M86-CF"] = "M86-CF"
    state: Literal["DORMANT", "UNAVAILABLE"] = "DORMANT"
    requested: bool = False
    enabled: Literal[False] = False
    observer: Optional[ProtectedWebhookOAuthObserver] = None
    observer_bound: Literal[False] = False
    activation_surface_available: Literal[False] = False
    execution_enabled: Literal[False] = False
    external_calls: Literal[0] = 0
    oauth_refresh_calls: Literal[0] = 0
    oauth_persistence_calls: Literal[0] = 0
    nia_calls: Literal[0] = 0
    bitrix_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False


def build_dormant_event_scoped_r1_mount(
    *,
    requested: bool = False,
    observer: Optional[ProtectedWebhookOAuthObserver] = None,
) -> EventScopedR1Mount:
    """Sólo compone ausencia; cualquier intento de habilitar falla cerrado."""

    if type(requested) is not bool:
        raise TypeError("event_r1_mount_request_invalid")
    if requested or observer is not None:
        return EventScopedR1Mount(
            state="UNAVAILABLE",
            requested=requested,
        )
    return EventScopedR1Mount()


__all__ = [
    "EventScopedR1Mount",
    "build_dormant_event_scoped_r1_mount",
]
