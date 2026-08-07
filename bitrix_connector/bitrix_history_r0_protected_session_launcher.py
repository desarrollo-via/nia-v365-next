"""Ensamblador real-ready no invocable para la sesión protegida R0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_armed_composition import (
    compose_stored_oauth_history_armed_reader,
)
from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_protected_handoff_composition import (
    prepare_protected_dotenv_history_handoff_once,
)
from .bitrix_history_r0_protected_session_entrypoint import (
    execute_protected_history_session_entrypoint_once,
)
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


SessionEntrypoint = Callable[..., object]
ProtectedOwnerPreparer = Callable[..., object]
ResourcesFactoryBuilder = Callable[..., object]
HistoryClientBuilder = Callable[..., object]
ArmedReaderComposer = Callable[..., object]


@dataclass(frozen=True)
class ProtectedHistorySessionLauncherPreviewSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_launcher_not_started"
    launcher_composed: bool = False
    session_entrypoint_bound: bool = False
    owner_preparer_bound: bool = False
    resources_factory_builder_bound: bool = False
    preflight_client_builder_bound: bool = False
    armed_reader_composer_bound: bool = False
    reader_client_builder_bound: bool = False
    source_open_calls: int = 0
    owner_calls: int = 0
    preflight_calls: int = 0
    confirmation_calls: int = 0
    reader_factory_calls: int = 0
    reader_calls: int = 0
    external_calls: int = 0


class PreparedProtectedHistorySessionLauncher:
    """Guarda referencias reales redactadas; deliberadamente no es invocable."""

    __slots__ = (
        "_armed_reader_composer",
        "_owner_preparer",
        "_preflight_client_builder",
        "_reader_client_builder",
        "_resources_factory_builder",
        "_session_entrypoint",
    )

    def __init__(
        self,
        *,
        session_entrypoint: SessionEntrypoint,
        owner_preparer: ProtectedOwnerPreparer,
        resources_factory_builder: ResourcesFactoryBuilder,
        preflight_client_builder: HistoryClientBuilder,
        armed_reader_composer: ArmedReaderComposer,
        reader_client_builder: HistoryClientBuilder,
    ) -> None:
        self._session_entrypoint = session_entrypoint
        self._owner_preparer = owner_preparer
        self._resources_factory_builder = resources_factory_builder
        self._preflight_client_builder = preflight_client_builder
        self._armed_reader_composer = armed_reader_composer
        self._reader_client_builder = reader_client_builder

    def __repr__(self) -> str:
        return "PreparedProtectedHistorySessionLauncher(<redacted>)"


def compose_real_ready_protected_history_session_launcher(
    *,
    session_entrypoint: SessionEntrypoint = (
        execute_protected_history_session_entrypoint_once
    ),
    owner_preparer: ProtectedOwnerPreparer = (
        prepare_protected_dotenv_history_handoff_once
    ),
    resources_factory_builder: ResourcesFactoryBuilder = (
        PilotDiscoveryOAuthFactory
    ),
    preflight_client_builder: HistoryClientBuilder = BitrixHistoryR0Client,
    armed_reader_composer: ArmedReaderComposer = (
        compose_stored_oauth_history_armed_reader
    ),
    reader_client_builder: HistoryClientBuilder = BitrixHistoryR0Client,
) -> PreparedProtectedHistorySessionLauncher:
    """Enlaza referencias sin construir fábricas, clientes, owners o lectores."""

    dependencies = (
        session_entrypoint,
        owner_preparer,
        resources_factory_builder,
        preflight_client_builder,
        armed_reader_composer,
        reader_client_builder,
    )
    if not all(callable(dependency) for dependency in dependencies):
        raise TypeError("protected_history_session_launcher_dependency_invalid")
    return PreparedProtectedHistorySessionLauncher(
        session_entrypoint=session_entrypoint,
        owner_preparer=owner_preparer,
        resources_factory_builder=resources_factory_builder,
        preflight_client_builder=preflight_client_builder,
        armed_reader_composer=armed_reader_composer,
        reader_client_builder=reader_client_builder,
    )


def preview_real_ready_protected_history_session_launcher(
    *,
    compose_launcher: Callable[
        [], PreparedProtectedHistorySessionLauncher
    ] = compose_real_ready_protected_history_session_launcher,
) -> ProtectedHistorySessionLauncherPreviewSnapshot:
    """Compone y descarta el launcher; nunca invoca sus referencias."""

    try:
        launcher = compose_launcher()
        if type(launcher) is not PreparedProtectedHistorySessionLauncher:
            raise TypeError("protected_history_session_launcher_invalid")
    except Exception:
        return ProtectedHistorySessionLauncherPreviewSnapshot(
            reason="protected_history_session_launcher_failed_safe"
        )
    return ProtectedHistorySessionLauncherPreviewSnapshot(
        state="PREPARED",
        reason="protected_history_session_launcher_prepared",
        launcher_composed=True,
        session_entrypoint_bound=True,
        owner_preparer_bound=True,
        resources_factory_builder_bound=True,
        preflight_client_builder_bound=True,
        armed_reader_composer_bound=True,
        reader_client_builder_bound=True,
    )


__all__ = [
    "ArmedReaderComposer",
    "HistoryClientBuilder",
    "PreparedProtectedHistorySessionLauncher",
    "ProtectedHistorySessionLauncherPreviewSnapshot",
    "ProtectedOwnerPreparer",
    "ResourcesFactoryBuilder",
    "SessionEntrypoint",
    "compose_real_ready_protected_history_session_launcher",
    "preview_real_ready_protected_history_session_launcher",
]
