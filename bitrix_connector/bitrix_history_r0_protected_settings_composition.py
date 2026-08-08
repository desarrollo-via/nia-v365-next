"""Composición hermética de settings desde una fuente dotenv inyectada."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from pathlib import Path

from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperSnapshot,
    ProtectedValueSource,
    ProtectedValueView,
    execute_protected_helper_once,
)
from .config import ConnectorSettings, load_settings
from .modes import ConnectorMode


ProtectedSettingsOperation = Callable[[ConnectorSettings], Awaitable[None]]
ProtectedSettingsLoader = Callable[[Mapping[str, str]], ConnectorSettings]
ProtectedSourceBuilder = Callable[[Path], ProtectedValueSource]


class _ProtectedSettingsEnvironment(Mapping[str, str]):
    """Mapping efímero: sólo expone al loader la allowlist aprobada."""

    __slots__ = ("_values",)

    def __init__(self, values: ProtectedValueView) -> None:
        self._values = values

    def __getitem__(self, name: str) -> str:
        if name not in PROTECTED_SETTING_NAMES:
            raise KeyError(name)
        return self._values.read_text(name)

    def __iter__(self) -> Iterator[str]:
        return iter(PROTECTED_SETTING_NAMES)

    def __len__(self) -> int:
        return len(PROTECTED_SETTING_NAMES)

    def __repr__(self) -> str:
        return "_ProtectedSettingsEnvironment(<redacted>)"


def _settings_are_safe(settings: object) -> bool:
    if type(settings) is not ConnectorSettings:
        return False
    protected_values_present = all(
        (
            settings.bitrix_domain,
            settings.bitrix_member_id,
            settings.bitrix_client_id,
            settings.bitrix_client_secret,
            settings.mongo_uri,
            settings.mongo_db,
            settings.installations_collection,
        )
    )
    return bool(
        protected_values_present
        and settings.requested_mode == ConnectorMode.OFF.value
        and settings.effective_mode is ConnectorMode.OFF
        and settings.activation_locked
        and not settings.external_calls_enabled
        and not settings.installation_enabled
        and settings.installation_configuration_valid
        and not settings.r0_bridge_enabled
        and settings.r0_bridge_configuration_valid
        and not settings.pilot_enabled
        and settings.pilot_emergency_stop
        and settings.pilot_configuration_valid
        and not settings.warnings
    )


async def execute_protected_dotenv_settings_once(
    *,
    dotenv_path: Path,
    operation: ProtectedSettingsOperation,
    settings_loader: ProtectedSettingsLoader = load_settings,
    source_builder: ProtectedSourceBuilder = AllowlistedDotenvSource,
) -> ProtectedHelperSnapshot:
    """Compone settings seguros y ejecuta una operación privada una sola vez."""

    source = source_builder(Path(dotenv_path))

    return await execute_protected_settings_once(
        source=source,
        operation=operation,
        settings_loader=settings_loader,
    )


async def execute_protected_settings_once(
    *,
    source: ProtectedValueSource,
    operation: ProtectedSettingsOperation,
    settings_loader: ProtectedSettingsLoader = load_settings,
) -> ProtectedHelperSnapshot:
    """Compone settings seguros desde cualquier fuente protegida inyectada."""

    if source is None or not callable(operation) or not callable(settings_loader):
        raise TypeError("protected_settings_composition_invalid")

    async def compose_and_execute(values: ProtectedValueView) -> None:
        environment = _ProtectedSettingsEnvironment(values)
        settings = settings_loader(environment)
        if not _settings_are_safe(settings):
            raise ValueError("protected_settings_barriers_invalid")
        operation_result = await operation(settings)
        if operation_result is not None:
            raise TypeError("protected_settings_operation_result_invalid")

    return await execute_protected_helper_once(
        source=source,
        operation=compose_and_execute,
    )


__all__ = [
    "ProtectedSettingsLoader",
    "ProtectedSettingsOperation",
    "ProtectedSourceBuilder",
    "execute_protected_dotenv_settings_once",
    "execute_protected_settings_once",
]
