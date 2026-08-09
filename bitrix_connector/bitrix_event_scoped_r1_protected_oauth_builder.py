"""Binding protegido real-ready para OAuth pre-evento, dormido por defecto."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Optional, Protocol

from .bitrix_event_scoped_r1_pre_event_oauth_adapter import (
    DormantStoredOAuthPreEventLeaseFactory,
)
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
    WindowsCredentialProtectedValueSource,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_protected_helper import ProtectedHelperState
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
    execute_protected_settings_once,
)
from .config import ConnectorSettings, load_settings
from .controlled_chat_participant_adapter import ParticipantSafetyState
from .controlled_chat_participant_http import (
    ControlledParticipantHttpResources,
    InjectedParticipantOAuthResources,
)
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS = 10.0


class StoredOAuthResourcesFactory(Protocol):
    async def build(
        self,
        settings: ConnectorSettings,
        *,
        timeout_seconds: float,
    ) -> InjectedParticipantOAuthResources: ...


class ProtectedStoredOAuthResourcesBuilder:
    """Lee el target exacto una vez y transfiere sólo el recurso OAuth."""

    __slots__ = (
        "_credential_backend",
        "_resources_factory",
        "_settings_loader",
        "_timeout_seconds",
        "_used",
    )

    def __init__(
        self,
        *,
        credential_backend: InjectedWindowsCredentialBackend,
        resources_factory: StoredOAuthResourcesFactory,
        timeout_seconds: float,
        settings_loader: ProtectedSettingsLoader = load_settings,
    ) -> None:
        if (
            credential_backend is None
            or not callable(getattr(credential_backend, "fetch_exact", None))
            or not callable(getattr(credential_backend, "close", None))
            or resources_factory is None
            or not callable(getattr(resources_factory, "build", None))
            or not callable(settings_loader)
            or timeout_seconds <= 0
        ):
            raise TypeError("pre_event_protected_oauth_dependency_invalid")
        self._credential_backend: Optional[InjectedWindowsCredentialBackend] = (
            credential_backend
        )
        self._resources_factory: Optional[StoredOAuthResourcesFactory] = (
            resources_factory
        )
        self._settings_loader = settings_loader
        self._timeout_seconds = timeout_seconds
        self._used = False

    async def __call__(self) -> InjectedParticipantOAuthResources:
        credential, self._credential_backend = self._credential_backend, None
        factory, self._resources_factory = self._resources_factory, None
        if self._used or credential is None or factory is None:
            self._used = True
            raise RuntimeError("pre_event_protected_oauth_builder_reused")
        self._used = True
        resources: Optional[InjectedParticipantOAuthResources] = None

        async def build_resources(settings: ConnectorSettings) -> None:
            nonlocal resources
            candidate = await factory.build(
                settings,
                timeout_seconds=self._timeout_seconds,
            )
            if not self._resources_valid(candidate):
                resources = candidate
                raise TypeError("pre_event_protected_oauth_resources_invalid")
            resources = candidate

        source = WindowsCredentialProtectedValueSource(backend=credential)
        snapshot = await execute_protected_settings_once(
            source=source,
            operation=build_resources,
            settings_loader=self._settings_loader,
        )
        self._settings_loader = lambda _values: None
        if (
            snapshot.state is ProtectedHelperState.READY
            and snapshot.resources_closed
            and snapshot.source_read_calls == 7
            and snapshot.operation_calls == 1
            and resources is not None
        ):
            return resources

        close_failed = False
        if resources is not None:
            try:
                await resources.close()
            except BaseException:
                close_failed = True
        resources = None
        if close_failed or not snapshot.resources_closed:
            raise RuntimeError("pre_event_protected_oauth_close_failed")
        if snapshot.state is ProtectedHelperState.CANCELLED:
            raise asyncio.CancelledError()
        raise RuntimeError("pre_event_protected_oauth_build_no_go")

    @staticmethod
    def _resources_valid(resources: object) -> bool:
        return bool(
            resources is not None
            and callable(getattr(resources, "close", None))
            and callable(
                getattr(
                    getattr(resources, "oauth_provider", None),
                    "get_access_token",
                    None,
                )
            )
            and type(getattr(resources, "portal_url", None)) is str
            and bool(getattr(resources, "portal_url", "").strip())
            and type(getattr(resources, "member_id", None)) is str
            and bool(getattr(resources, "member_id", "").strip())
        )

    def __repr__(self) -> str:
        return "ProtectedStoredOAuthResourcesBuilder(<redacted>)"


def build_dormant_real_pre_event_lease_factory(
    *,
    safety: ParticipantSafetyState,
    timeout_seconds: float = PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    credential_backend_builder=build_real_windows_credential_backend,
    resources_factory_builder=PilotDiscoveryOAuthFactory,
    http_resources_factory=ControlledParticipantHttpResources.build,
) -> DormantStoredOAuthPreEventLeaseFactory:
    """Enlaza factories reales sin leer credenciales, Mongo ni OAuth."""

    if (
        not callable(credential_backend_builder)
        or not callable(resources_factory_builder)
    ):
        raise TypeError("pre_event_protected_oauth_binding_invalid")
    builder = ProtectedStoredOAuthResourcesBuilder(
        credential_backend=credential_backend_builder(),
        resources_factory=resources_factory_builder(),
        timeout_seconds=timeout_seconds,
    )
    return DormantStoredOAuthPreEventLeaseFactory(
        safety=safety,
        resources_builder=builder,
        timeout_seconds=timeout_seconds,
        clock=clock,
        http_resources_factory=http_resources_factory,
    )


__all__ = [
    "PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS",
    "ProtectedStoredOAuthResourcesBuilder",
    "StoredOAuthResourcesFactory",
    "build_dormant_real_pre_event_lease_factory",
]
