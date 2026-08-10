"""Adaptador dormido para construir el lease desde OAuth protegido."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Optional, Protocol

from .bitrix_event_scoped_r1_pre_event_lease import (
    PreEventLeaseArmEvidence,
    PreEventLeaseRollbackEvidence,
    PreEventParticipantLease,
)
from .bitrix_event_scoped_r1_pre_event_lease_factory import (
    FAILED_FINGERPRINT,
    InjectedPreEventLeaseOperations,
)
from .controlled_chat_participant_adapter import ParticipantSafetyState
from .controlled_chat_participant_http import (
    ControlledParticipantHttpResources,
    InjectedParticipantOAuthResources,
)


class ProtectedParticipantOAuthResourcesBuilder(Protocol):
    async def __call__(self) -> InjectedParticipantOAuthResources: ...


class _StoredAccessOnlyProvider:
    """Expone únicamente una lectura almacenada y one-shot."""

    __slots__ = ("_member_id", "_provider", "_used")

    def __init__(self, provider: object, *, member_id: str) -> None:
        if not callable(getattr(provider, "get_access_token", None)):
            raise TypeError("pre_event_oauth_provider_invalid")
        self._provider: Optional[object] = provider
        self._member_id = member_id
        self._used = False

    async def get_access_token(self, member_id: str) -> str:
        provider = self._provider
        if self._used or provider is None or member_id != self._member_id:
            self._used = True
            raise RuntimeError("pre_event_oauth_read_unavailable")
        self._used = True
        token = await provider.get_access_token(member_id)
        if type(token) is not str or not token.strip() or "\x00" in token:
            raise ValueError("pre_event_oauth_token_invalid")
        return token

    def close(self) -> None:
        self._provider = None
        self._member_id = ""
        self._used = True

    def __repr__(self) -> str:
        return "_StoredAccessOnlyProvider(<redacted>)"


class _OwnedParticipantOAuthResources:
    """Transfiere al lease la propiedad y cierre de los recursos originales."""

    __slots__ = (
        "_closed",
        "_owned",
        "member_id",
        "oauth_provider",
        "portal_url",
    )

    def __init__(self, owned: object) -> None:
        portal_url = getattr(owned, "portal_url", None)
        member_id = getattr(owned, "member_id", None)
        close = getattr(owned, "close", None)
        if (
            type(portal_url) is not str
            or not portal_url.strip()
            or type(member_id) is not str
            or not member_id.strip()
            or not callable(close)
        ):
            raise TypeError("pre_event_oauth_resources_invalid")
        self._owned: Optional[object] = owned
        self._closed = False
        self.portal_url = portal_url
        self.member_id = member_id
        self.oauth_provider = _StoredAccessOnlyProvider(
            getattr(owned, "oauth_provider", None),
            member_id=member_id,
        )

    async def close(self) -> None:
        owned, self._owned = self._owned, None
        if self._closed:
            return
        self._closed = True
        self.oauth_provider.close()
        self.portal_url = ""
        self.member_id = ""
        if owned is not None:
            await owned.close()

    def __repr__(self) -> str:
        return "_OwnedParticipantOAuthResources(<redacted>)"


class _LazyPreEventOAuthOperations:
    """Abre OAuth sólo al armar y delega su cierre al rollback."""

    def __init__(
        self,
        *,
        safety: ParticipantSafetyState,
        resources_builder: ProtectedParticipantOAuthResourcesBuilder,
        timeout_seconds: float,
        http_resources_factory,
    ) -> None:
        self._safety = safety
        self._resources_builder: Optional[
            ProtectedParticipantOAuthResourcesBuilder
        ] = resources_builder
        self._timeout_seconds = timeout_seconds
        self._http_resources_factory = http_resources_factory
        self._delegate: Optional[InjectedPreEventLeaseOperations] = None
        self._arm_used = False
        self._rollback_used = False

    async def arm(self) -> PreEventLeaseArmEvidence:
        builder, self._resources_builder = self._resources_builder, None
        if self._arm_used or builder is None:
            raise RuntimeError("pre_event_oauth_arm_unavailable")
        self._arm_used = True
        raw: Optional[object] = None
        try:
            raw = await builder()
            owned = _OwnedParticipantOAuthResources(raw)
            raw = None
            delegate = InjectedPreEventLeaseOperations(
                safety=self._safety,
                oauth_resources=owned,
                timeout_seconds=self._timeout_seconds,
                http_resources_factory=self._http_resources_factory,
            )
            self._delegate = delegate
            return await delegate.arm()
        except BaseException:
            if raw is not None and callable(getattr(raw, "close", None)):
                await raw.close()
            raise

    async def rollback(
        self, expected_fingerprint: Optional[str]
    ) -> PreEventLeaseRollbackEvidence:
        if self._rollback_used:
            raise RuntimeError("pre_event_oauth_rollback_reused")
        self._rollback_used = True
        delegate, self._delegate = self._delegate, None
        self._resources_builder = None
        self._http_resources_factory = lambda **_kwargs: None
        if delegate is None:
            return PreEventLeaseRollbackEvidence(
                exact_scope=False,
                restored_verified=False,
                bot_next_absent=False,
                bot_nia_absent=False,
                restored_fingerprint=FAILED_FINGERPRINT,
            )
        return await delegate.rollback(expected_fingerprint)

    def __repr__(self) -> str:
        return "_LazyPreEventOAuthOperations(<redacted>)"


class DormantStoredOAuthPreEventLeaseFactory:
    """Fábrica one-shot sin apertura hasta la segunda confirmación."""

    def __init__(
        self,
        *,
        safety: ParticipantSafetyState,
        resources_builder: ProtectedParticipantOAuthResourcesBuilder,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        http_resources_factory=ControlledParticipantHttpResources.build,
    ) -> None:
        if (
            not callable(resources_builder)
            or not callable(clock)
            or not callable(http_resources_factory)
            or timeout_seconds <= 0
        ):
            raise TypeError("pre_event_oauth_factory_dependency_invalid")
        self._safety = safety
        self._resources_builder: Optional[
            ProtectedParticipantOAuthResourcesBuilder
        ] = resources_builder
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._http_resources_factory = http_resources_factory
        self._used = False

    def __call__(self) -> PreEventParticipantLease:
        builder, self._resources_builder = self._resources_builder, None
        if self._used or builder is None:
            raise RuntimeError("pre_event_oauth_factory_reused")
        self._used = True
        operations = _LazyPreEventOAuthOperations(
            safety=self._safety,
            resources_builder=builder,
            timeout_seconds=self._timeout_seconds,
            http_resources_factory=self._http_resources_factory,
        )
        self._http_resources_factory = lambda **_kwargs: None
        return PreEventParticipantLease(
            safety=self._safety,
            arm=operations.arm,
            rollback=operations.rollback,
            clock=self._clock,
        )

    def __repr__(self) -> str:
        return "DormantStoredOAuthPreEventLeaseFactory(<redacted>)"


__all__ = [
    "DormantStoredOAuthPreEventLeaseFactory",
    "ProtectedParticipantOAuthResourcesBuilder",
]
