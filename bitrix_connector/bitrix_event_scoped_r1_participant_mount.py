"""Montaje one-shot de participantes alrededor del roundtrip R1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional, Protocol

from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)
from .bitrix_history_r0_m86_concrete_lifecycle_operations import (
    M86I_TIMEOUT_SECONDS,
    _https_origin,
)
from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .config import ConnectorSettings
from .controlled_chat_participant_adapter import (
    ParticipantAdapterStatus,
    ParticipantSafetyState,
)
from .controlled_chat_participant_http import (
    ControlledParticipantHttpResources,
    rehearse_controlled_participant_with_injected_oauth,
)
from .models import NormalizedBitrixEvent


class EventR1InnerRoundtrip(Protocol):
    async def __call__(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
        outcome: BitrixHistoryR0PreflightOutcome,
        event: NormalizedBitrixEvent,
    ) -> object: ...


class _BorrowedEventTokenProvider:
    def __init__(
        self,
        *,
        token_view: StoredOAuthAccessView,
        member_id: str,
    ) -> None:
        self._token_view: Optional[StoredOAuthAccessView] = token_view
        self._member_id = member_id
        self._used = False

    async def get_access_token(self, member_id: str) -> str:
        if (
            self._used
            or self._token_view is None
            or member_id != self._member_id
        ):
            raise RuntimeError("event_r1_participant_token_unavailable")
        self._used = True
        return self._token_view.read_text()

    def close(self) -> None:
        self._token_view = None
        self._member_id = ""

    def __repr__(self) -> str:
        return "_BorrowedEventTokenProvider(<redacted>)"


class _BorrowedEventOAuthResources:
    def __init__(
        self,
        *,
        token_view: StoredOAuthAccessView,
        portal_url: str,
        member_id: str,
    ) -> None:
        self.oauth_provider = _BorrowedEventTokenProvider(
            token_view=token_view,
            member_id=member_id,
        )
        self.portal_url = portal_url
        self.member_id = member_id
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.oauth_provider.close()
        self.portal_url = ""
        self.member_id = ""

    def __repr__(self) -> str:
        return "_BorrowedEventOAuthResources(<redacted>)"


@dataclass(frozen=True)
class EventR1ParticipantMountFailure:
    phase: Literal["M86-CP"] = "M86-CP"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "event_r1_participant_mount_failed_safe"
    participant_status: str = "blocked"
    add_attempts: int = 0
    work_attempts: int = 0
    rollback_attempts: int = 0
    rollback_verified: bool = False
    retry_budget: Literal[0] = 0
    oauth_refresh_calls: Literal[0] = 0
    oauth_persistence_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False


class EventR1ParticipantMountedRoundtrip:
    """Añade Bot Next, ejecuta el roundtrip y restaura antes de retornar."""

    def __init__(
        self,
        *,
        roundtrip: EventR1InnerRoundtrip,
        timeout_seconds: float = M86I_TIMEOUT_SECONDS,
        http_resources_factory: Callable[..., object] = (
            ControlledParticipantHttpResources.build
        ),
    ) -> None:
        if (
            not callable(roundtrip)
            or timeout_seconds <= 0
            or not callable(http_resources_factory)
        ):
            raise TypeError("event_r1_participant_mount_dependency_invalid")
        self._roundtrip: Optional[EventR1InnerRoundtrip] = roundtrip
        self._timeout_seconds = timeout_seconds
        self._http_resources_factory = http_resources_factory
        self._used = False

    async def __call__(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
        outcome: BitrixHistoryR0PreflightOutcome,
        event: NormalizedBitrixEvent,
    ) -> object:
        roundtrip, self._roundtrip = self._roundtrip, None
        if self._used or roundtrip is None:
            return EventR1ParticipantMountFailure(
                reason="event_r1_participant_mount_already_used"
            )
        self._used = True

        member_id = (settings.bitrix_member_id or "").strip()
        if not member_id:
            return EventR1ParticipantMountFailure(
                reason="event_r1_participant_member_missing"
            )
        try:
            portal_url = _https_origin(
                settings.bitrix_domain,
                reason="event_r1_participant_portal_invalid",
            )
        except ValueError:
            return EventR1ParticipantMountFailure(
                reason="event_r1_participant_portal_invalid"
            )

        safety = ParticipantSafetyState(
            effective_mode=settings.effective_mode.value,
            activation_locked=settings.activation_locked,
            external_calls_enabled=settings.external_calls_enabled,
            runtime_state="inert",
            r0_mounted=settings.r0_bridge_enabled,
            r1_active=settings.event_r1_enabled,
        )
        work_results: list[object] = []

        async def while_linked() -> object:
            result = await roundtrip(settings, token_view, outcome, event)
            work_results.append(result)
            return result

        oauth_resources = _BorrowedEventOAuthResources(
            token_view=token_view,
            portal_url=portal_url,
            member_id=member_id,
        )
        participant = (
            await rehearse_controlled_participant_with_injected_oauth(
                safety=safety,
                oauth_resources=oauth_resources,
                timeout_seconds=self._timeout_seconds,
                while_linked=while_linked,
                http_resources_factory=self._http_resources_factory,
            )
        )
        self._http_resources_factory = lambda **_kwargs: None

        if (
            participant.status is ParticipantAdapterStatus.RESTORED
            and participant.work_completed
            and participant.rollback_verified
            and len(work_results) == 1
        ):
            return work_results[0]
        return EventR1ParticipantMountFailure(
            reason="event_r1_participant_mount_failed_safe",
            participant_status=participant.status.value,
            add_attempts=participant.add_attempts,
            work_attempts=participant.work_attempts,
            rollback_attempts=participant.rollback_attempts,
            rollback_verified=participant.rollback_verified,
        )

    def __repr__(self) -> str:
        return "EventR1ParticipantMountedRoundtrip(<redacted>)"


__all__ = [
    "EventR1ParticipantMountFailure",
    "EventR1ParticipantMountedRoundtrip",
]
