"""Montaje R1 apagado por defecto y activable sólo bajo contrato exacto."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Literal, Optional

import httpx
from fastapi import APIRouter

from .bitrix_event_scoped_r1_control import (
    EVENT_R1_CONTROL_PREFIX,
    EventScopedR1SessionOwner,
    build_event_r1_control_router,
)
from .bitrix_event_scoped_r1_gate import EventScopedR1Gate
from .bitrix_event_scoped_r1_participant_mount import (
    EventR1ParticipantMountedRoundtrip,
)
from .bitrix_event_scoped_r1_pre_event_lease import PreEventParticipantLease
from .bitrix_history_r0_m86_concrete_lifecycle_operations import (
    M86ConcreteLifecycleOperations,
)
from .config import ConnectorMode, ConnectorSettings
from .review_auth import SingleReviewerAuthenticator
from .webhook_handler import ProtectedWebhookOAuthObserver


@dataclass(frozen=True)
class EventScopedR1Mount:
    phase: Literal["M86-CF"] = "M86-CF"
    state: Literal["DORMANT", "MOUNTED", "UNAVAILABLE"] = "DORMANT"
    requested: bool = False
    enabled: bool = False
    router: Optional[APIRouter] = None
    observer: Optional[ProtectedWebhookOAuthObserver] = None
    owner: Optional[EventScopedR1SessionOwner] = None
    observer_bound: bool = False
    activation_surface_available: bool = False
    execution_enabled: bool = False
    participant_roundtrip_bound: bool = False
    pre_event_lease_factory_bound: bool = False
    participant_strategy: Literal["none", "posterior", "pre-event"] = "none"
    participant_mount_count: int = 0
    status: str = "disabled"
    reason: str = "event_r1_disabled"
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


class EventR1MountConfigurationError(RuntimeError):
    """Impide montar una activación incompleta o fuera de las barreras."""


_SAFE_CONFIGURATION_REASONS = frozenset(
    {
        "event_r1_switch_invalid",
        "event_r1_safety_state_invalid",
        "event_r1_review_auth_missing",
        "event_r1_dependency_missing",
        "event_r1_owner_factory_invalid",
        "event_r1_participant_strategy_ambiguous",
    }
)


async def _production_http_client_factory(
    _name: str, timeout_seconds: float
) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_seconds)


async def _unreachable_cross_turn(*_args) -> None:
    raise RuntimeError("event_r1_cross_turn_not_available")


def _production_gate_factory(
    settings: ConnectorSettings,
    *,
    posterior_participant_mount: bool = True,
) -> EventScopedR1Gate:
    operations = M86ConcreteLifecycleOperations(
        nia_base_url=settings.nia_base_url or "",
        http_client_factory=_production_http_client_factory,
        cross_turn_waiter=_unreachable_cross_turn,
        emergency_rollback=True,
    )
    roundtrip = operations.m88_event
    if posterior_participant_mount:
        roundtrip = EventR1ParticipantMountedRoundtrip(roundtrip=roundtrip)
    return EventScopedR1Gate(
        preflight=operations.preflight,
        roundtrip=roundtrip,
        execution_enabled=True,
    )


def build_optional_event_scoped_r1_mount(
    settings: ConnectorSettings,
    *,
    prefix: str = EVENT_R1_CONTROL_PREFIX,
    owner_factory: Callable[..., EventScopedR1SessionOwner] = (
        EventScopedR1SessionOwner
    ),
    gate_factory: Optional[Callable[[], EventScopedR1Gate]] = None,
    pre_event_lease_factory: Optional[
        Callable[[], PreEventParticipantLease]
    ] = None,
) -> EventScopedR1Mount:
    """Compone una única sesión protegida sin desbloquear el conector."""

    if not settings.event_r1_configuration_valid:
        raise EventR1MountConfigurationError("event_r1_switch_invalid")
    if not settings.event_r1_enabled:
        return build_dormant_event_scoped_r1_mount()
    if (
        settings.requested_mode != ConnectorMode.OFF.value
        or settings.effective_mode is not ConnectorMode.OFF
        or not settings.activation_locked
        or settings.external_calls_enabled
        or settings.pilot_enabled
        or not settings.pilot_emergency_stop
        or not settings.pilot_configuration_valid
        or settings.r0_bridge_enabled
    ):
        raise EventR1MountConfigurationError("event_r1_safety_state_invalid")
    if not all(
        (
            settings.nia_base_url,
            settings.bitrix_domain,
            settings.bitrix_member_id,
            settings.bitrix_application_token,
        )
    ):
        raise EventR1MountConfigurationError("event_r1_dependency_missing")

    authenticator = SingleReviewerAuthenticator(
        review_token=settings.review_token,
        actor=settings.review_actor,
        credential_id=settings.review_credential_id,
    )
    if not authenticator.configured:
        raise EventR1MountConfigurationError("event_r1_review_auth_missing")

    if gate_factory is not None and pre_event_lease_factory is not None:
        raise EventR1MountConfigurationError(
            "event_r1_participant_strategy_ambiguous"
        )

    participant_strategy: Literal["none", "posterior", "pre-event"]
    if gate_factory is not None:
        participant_strategy = "none"
        factory = gate_factory
    elif pre_event_lease_factory is not None:
        participant_strategy = "pre-event"
        factory = lambda: _production_gate_factory(
            settings, posterior_participant_mount=False
        )
    else:
        participant_strategy = "posterior"
        factory = lambda: _production_gate_factory(settings)
    try:
        if pre_event_lease_factory is None:
            owner = owner_factory(factory)
        else:
            owner = owner_factory(
                factory,
                pre_event_lease_factory=pre_event_lease_factory,
            )
    except Exception as exc:
        raise EventR1MountConfigurationError(
            "event_r1_owner_factory_invalid"
        ) from exc
    if not isinstance(owner, EventScopedR1SessionOwner):
        raise EventR1MountConfigurationError("event_r1_owner_factory_invalid")

    return EventScopedR1Mount(
        state="MOUNTED",
        requested=True,
        enabled=True,
        router=build_event_r1_control_router(
            owner,
            authenticator,
            prefix=prefix,
        ),
        observer=owner.observe,
        owner=owner,
        observer_bound=True,
        activation_surface_available=True,
        execution_enabled=True,
        participant_roundtrip_bound=participant_strategy == "posterior",
        pre_event_lease_factory_bound=participant_strategy == "pre-event",
        participant_strategy=participant_strategy,
        participant_mount_count=(
            0 if participant_strategy == "none" else 1
        ),
        status="mounted",
        reason="event_r1_mounted",
    )


def mount_optional_event_scoped_r1_fail_isolated(
    parent_router: APIRouter,
    settings: ConnectorSettings,
    *,
    prefix: str = EVENT_R1_CONTROL_PREFIX,
    owner_factory: Callable[..., EventScopedR1SessionOwner] = (
        EventScopedR1SessionOwner
    ),
    gate_factory: Optional[Callable[[], EventScopedR1Gate]] = None,
    pre_event_lease_factory: Optional[
        Callable[[], PreEventParticipantLease]
    ] = None,
) -> EventScopedR1Mount:
    """Aísla configuración inválida y conserva el webhook inerte."""

    try:
        mount = build_optional_event_scoped_r1_mount(
            settings,
            prefix=prefix,
            owner_factory=owner_factory,
            gate_factory=gate_factory,
            pre_event_lease_factory=pre_event_lease_factory,
        )
    except EventR1MountConfigurationError as exc:
        candidate = str(exc)
        reason = (
            candidate
            if candidate in _SAFE_CONFIGURATION_REASONS
            else "event_r1_configuration_invalid"
        )
        return EventScopedR1Mount(
            state="UNAVAILABLE",
            requested=settings.event_r1_enabled,
            status="unavailable",
            reason=reason,
        )
    if mount.router is not None:
        parent_router.include_router(mount.router)
    return mount


__all__ = [
    "EventScopedR1Mount",
    "EventR1MountConfigurationError",
    "build_optional_event_scoped_r1_mount",
    "build_dormant_event_scoped_r1_mount",
    "mount_optional_event_scoped_r1_fail_isolated",
]
