"""Selección fail-closed del montaje posterior o pre-evento R1."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from .bitrix_event_scoped_r1_control import EVENT_R1_CONTROL_PREFIX
from .bitrix_event_scoped_r1_mount import (
    EventScopedR1Mount,
    mount_optional_event_scoped_r1_fail_isolated,
)
from .bitrix_event_scoped_r1_pre_event_lease import PreEventParticipantLease
from .r1_key_vault_pre_event_oauth_builder import (
    build_dormant_key_vault_pre_event_lease_factory,
)
from .config import (
    EVENT_R1_PARTICIPANT_STRATEGY_POSTERIOR,
    EVENT_R1_PARTICIPANT_STRATEGY_PRE_EVENT,
    ConnectorSettings,
)
from .controlled_chat_participant_adapter import ParticipantSafetyState


PRE_EVENT_BINDING_INVALID_REASON = (
    "event_r1_participant_strategy_invalid"
)
PRE_EVENT_BINDING_UNAVAILABLE_REASON = (
    "event_r1_pre_event_binding_unavailable"
)


def _unavailable(
    settings: ConnectorSettings,
    *,
    reason: str,
) -> EventScopedR1Mount:
    return EventScopedR1Mount(
        state="UNAVAILABLE",
        requested=settings.event_r1_enabled,
        status="unavailable",
        reason=reason,
    )


def _participant_safety(settings: ConnectorSettings) -> ParticipantSafetyState:
    return ParticipantSafetyState(
        effective_mode=settings.effective_mode.value,
        activation_locked=settings.activation_locked,
        external_calls_enabled=settings.external_calls_enabled,
        runtime_state="inert",
        r0_mounted=settings.r0_bridge_enabled,
        r1_active=settings.event_r1_enabled,
    )


def mount_optional_event_scoped_r1_with_pre_event_binding(
    parent_router: APIRouter,
    settings: ConnectorSettings,
    *,
    prefix: str = EVENT_R1_CONTROL_PREFIX,
    lease_factory_builder: Callable[..., Callable[
        [], PreEventParticipantLease
    ]] = build_dormant_key_vault_pre_event_lease_factory,
) -> EventScopedR1Mount:
    """Selecciona estrategia sin abrir Credential Manager, Mongo, OAuth o HTTP."""

    if not settings.event_r1_participant_strategy_configuration_valid:
        return _unavailable(
            settings,
            reason=PRE_EVENT_BINDING_INVALID_REASON,
        )

    if not settings.event_r1_enabled:
        return mount_optional_event_scoped_r1_fail_isolated(
            parent_router,
            settings,
            prefix=prefix,
        )

    pre_event_factory = None
    if (
        settings.event_r1_participant_strategy
        == EVENT_R1_PARTICIPANT_STRATEGY_PRE_EVENT
    ):
        if not callable(lease_factory_builder):
            return _unavailable(
                settings,
                reason=PRE_EVENT_BINDING_UNAVAILABLE_REASON,
            )
        try:
            pre_event_factory = lease_factory_builder(
                safety=_participant_safety(settings),
                vault_url=settings.key_vault_url,
            )
        except Exception:
            return _unavailable(
                settings,
                reason=PRE_EVENT_BINDING_UNAVAILABLE_REASON,
            )
        if not callable(pre_event_factory):
            return _unavailable(
                settings,
                reason=PRE_EVENT_BINDING_UNAVAILABLE_REASON,
            )
    elif (
        settings.event_r1_participant_strategy
        != EVENT_R1_PARTICIPANT_STRATEGY_POSTERIOR
    ):
        return _unavailable(
            settings,
            reason=PRE_EVENT_BINDING_INVALID_REASON,
        )

    return mount_optional_event_scoped_r1_fail_isolated(
        parent_router,
        settings,
        prefix=prefix,
        pre_event_lease_factory=pre_event_factory,
    )


__all__ = [
    "PRE_EVENT_BINDING_INVALID_REASON",
    "PRE_EVENT_BINDING_UNAVAILABLE_REASON",
    "mount_optional_event_scoped_r1_with_pre_event_binding",
]
