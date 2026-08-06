"""Owner one-shot para una renovación OAuth protegida y sin lecturas Bitrix."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_helper import ProtectedHelperState
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
    ProtectedSourceBuilder,
    execute_protected_dotenv_settings_once,
)
from .config import ConnectorSettings, load_settings
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


OAUTH_REFRESH_REAL_CONFIRMATION = "RENOVAR OAUTH R0 PROTEGIDO UNA SOLA VEZ"
OAUTH_REFRESH_OWNER_MODULE = (
    "bitrix_connector.bitrix_oauth_refresh_execution_owner"
)
OAUTH_REFRESH_OWNER_COMMAND = (
    r'.\.venv\Scripts\python.exe -m '
    r'bitrix_connector.bitrix_oauth_refresh_execution_owner '
    r'--confirm-code "RENOVAR OAUTH R0 PROTEGIDO UNA SOLA VEZ" '
    r'--dotenv-path .env'
)
OAUTH_REFRESH_FUTURE_AUTHORIZATION = (
    "AUTORIZACIÓN INDEPENDIENTE R0 — RENOVACIÓN OAUTH PROTEGIDA ÚNICA: "
    "Autorizo exclusivamente, después de verificar que el owner "
    "bitrix_connector.bitrix_oauth_refresh_execution_owner figura "
    "command_available=true y owner_module_invocable=true, una ejecución única "
    "mediante el comando exacto congelado .\\.venv\\Scripts\\python.exe -m "
    "bitrix_connector.bitrix_oauth_refresh_execution_owner --confirm-code "
    "\"RENOVAR OAUTH R0 PROTEGIDO UNA SOLA VEZ\" --dotenv-path .env. "
    "Autorizo una sola apertura interna de "
    "C:\\Users\\H\\Desktop\\f\\web\\phyton-codigo\\nia-next\\.env por "
    "AllowlistedDotenvSource para transferir únicamente NIA_BITRIX_DOMAIN, "
    "NIA_BITRIX_MEMBER_ID, NIA_BITRIX_CLIENT_ID, NIA_BITRIX_CLIENT_SECRET, "
    "NIA_BITRIX_MONGO_URI, NIA_BITRIX_MONGO_DB y "
    "NIA_BITRIX_INSTALLATIONS_COLLECTION, sin mostrar, copiar, transcribir, "
    "contar, validar ni registrar sus valores. Autorizo acceder únicamente a la "
    "instalación OAuth identificada por el member_id protegido, invocar "
    "BitrixOAuthCredentialProvider.refresh_access_token exactamente una vez, "
    "realizar una sola solicitud al endpoint OAuth de renovación y persistir de "
    "forma condicional el par rotado. Se permite una verificación final interna "
    "y redactada de persistencia. La salida queda limitada a estados, booleanos "
    "y contadores allowlisted; no puede mostrar valores, fragmentos, longitudes, "
    "hashes, respuestas OAuth, URLs autenticadas ni excepciones privadas. No "
    "autorizo reintentos, métodos REST de Bitrix, historial, mensajes, "
    "config.update, bots, Línea 13, Wazzup, Azure, NIA, armado del lector ni "
    "solicitud o envío de mensajes. Cualquier fuente, identidad, renovación, "
    "persistencia, salida, timeout, error, conflicto, cancelación o cierre "
    "ambiguo obliga a detenerse, limpiar en finally y terminar en fallo seguro; "
    "no existe rollback sobre Bitrix porque no se modifica su estructura."
)
DEFAULT_OAUTH_REFRESH_TIMEOUT_SECONDS = 10.0


class OAuthRefreshProvider(Protocol):
    async def get_access_token(self, member_id: str) -> str: ...

    async def refresh_access_token(
        self,
        member_id: str,
        stale_access_token: str,
    ) -> str: ...


class OAuthRefreshResources(Protocol):
    oauth_provider: OAuthRefreshProvider
    member_id: str

    async def close(self) -> None: ...


class OAuthRefreshResourcesFactory(Protocol):
    async def build(
        self,
        settings: ConnectorSettings,
        *,
        timeout_seconds: float,
    ) -> OAuthRefreshResources: ...


@dataclass(frozen=True)
class OAuthRefreshOwnerReadiness:
    owner_module: str = OAUTH_REFRESH_OWNER_MODULE
    owner_command: str = OAUTH_REFRESH_OWNER_COMMAND
    command_available: bool = True
    owner_module_invocable: bool = True
    authorization_ready_for_use: bool = False
    two_confirmations_required: Literal[True] = True
    exact_rollback_available: Literal[False] = False
    real_execution_authorized: bool = False
    source_open_authorized: bool = False
    oauth_refresh_authorized: bool = False
    bitrix_api_calls_authorized: bool = False
    retry_authorized: bool = False


@dataclass(frozen=True)
class OAuthRefreshExecutionSnapshot:
    state: Literal["READY", "NO-GO", "CANCELLED"] = "NO-GO"
    reason: str = "oauth_refresh_owner_not_started"
    protected_source_opened: bool = False
    required_values_present: bool = False
    resources_closed: bool = True
    source_read_calls: int = 0
    settings_operation_calls: int = 0
    resource_build_calls: int = 0
    access_token_read_calls: int = 0
    refresh_method_calls: int = 0
    persistence_verification_calls: int = 0
    token_rotated: bool = False
    persistence_verified: bool = False
    bitrix_api_calls: int = 0
    history_read_calls: int = 0
    mutation_calls: int = 0
    nia_called: bool = False
    bitrix_written: bool = False


OAUTH_REFRESH_OWNER_READINESS = OAuthRefreshOwnerReadiness()


async def execute_protected_oauth_refresh_once(
    *,
    dotenv_path: Path,
    resources_factory: OAuthRefreshResourcesFactory | None = None,
    timeout_seconds: float = DEFAULT_OAUTH_REFRESH_TIMEOUT_SECONDS,
    settings_loader: ProtectedSettingsLoader = load_settings,
    source_builder: ProtectedSourceBuilder = AllowlistedDotenvSource,
) -> OAuthRefreshExecutionSnapshot:
    """Renueva una vez; nunca construye un cliente REST de Bitrix."""

    if (
        type(timeout_seconds) not in {int, float}
        or timeout_seconds <= 0
        or timeout_seconds > DEFAULT_OAUTH_REFRESH_TIMEOUT_SECONDS
    ):
        return OAuthRefreshExecutionSnapshot(reason="oauth_refresh_timeout_invalid")

    selected_factory: OAuthRefreshResourcesFactory = (
        resources_factory or PilotDiscoveryOAuthFactory()
    )
    resource_build_calls = 0
    access_token_read_calls = 0
    refresh_method_calls = 0
    persistence_verification_calls = 0
    oauth_resources_closed = True
    token_rotated = False
    persistence_verified = False

    async def refresh(settings: ConnectorSettings) -> None:
        nonlocal resource_build_calls
        nonlocal access_token_read_calls
        nonlocal refresh_method_calls
        nonlocal persistence_verification_calls
        nonlocal oauth_resources_closed
        nonlocal token_rotated
        nonlocal persistence_verified

        resources: OAuthRefreshResources | None = None
        resource_build_calls = 1
        try:
            resources = await selected_factory.build(
                settings,
                timeout_seconds=float(timeout_seconds),
            )
            oauth_resources_closed = False
            access_token_read_calls = 1
            stale_token = await resources.oauth_provider.get_access_token(
                resources.member_id
            )
            refresh_method_calls = 1
            refreshed_token = await resources.oauth_provider.refresh_access_token(
                resources.member_id,
                stale_token,
            )
            persistence_verification_calls = 1
            persisted_token = await resources.oauth_provider.get_access_token(
                resources.member_id
            )
            token_rotated = bool(refreshed_token != stale_token)
            persistence_verified = bool(
                token_rotated and persisted_token == refreshed_token
            )
            if not persistence_verified:
                raise RuntimeError("oauth_refresh_persistence_not_verified")
        finally:
            stale_token = None
            refreshed_token = None
            persisted_token = None
            if resources is not None:
                await resources.close()
                oauth_resources_closed = True

    helper = await execute_protected_dotenv_settings_once(
        dotenv_path=Path(dotenv_path),
        operation=refresh,
        settings_loader=settings_loader,
        source_builder=source_builder,
    )
    resources_closed = bool(helper.resources_closed and oauth_resources_closed)
    ready = bool(
        helper.state is ProtectedHelperState.READY
        and resources_closed
        and resource_build_calls == 1
        and access_token_read_calls == 1
        and refresh_method_calls == 1
        and persistence_verification_calls == 1
        and token_rotated
        and persistence_verified
    )
    if ready:
        state: Literal["READY", "NO-GO", "CANCELLED"] = "READY"
        reason = "oauth_rotated_and_persisted"
    elif helper.state is ProtectedHelperState.CANCELLED:
        state = "CANCELLED"
        reason = "oauth_refresh_cancelled"
    elif not resources_closed:
        state = "NO-GO"
        reason = "oauth_refresh_resources_close_failed"
    else:
        state = "NO-GO"
        reason = "oauth_refresh_failed_safe"

    return OAuthRefreshExecutionSnapshot(
        state=state,
        reason=reason,
        protected_source_opened=helper.protected_source_opened,
        required_values_present=helper.required_values_present,
        resources_closed=resources_closed,
        source_read_calls=helper.source_read_calls,
        settings_operation_calls=helper.operation_calls,
        resource_build_calls=resource_build_calls,
        access_token_read_calls=access_token_read_calls,
        refresh_method_calls=refresh_method_calls,
        persistence_verification_calls=persistence_verification_calls,
        token_rotated=token_rotated if ready else False,
        persistence_verified=persistence_verified if ready else False,
    )


OAuthRefreshExecutor = Callable[..., Any]


def _parse_request(argv: Sequence[str]) -> Path | None:
    values = tuple(argv)
    if (
        len(values) != 4
        or values[0] != "--confirm-code"
        or values[1] != OAUTH_REFRESH_REAL_CONFIRMATION
        or values[2] != "--dotenv-path"
        or not values[3]
    ):
        return None
    try:
        return Path(values[3])
    except (TypeError, ValueError):
        return None


def _emit(snapshot: OAuthRefreshExecutionSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    executor: OAuthRefreshExecutor = execute_protected_oauth_refresh_once,
) -> int:
    """Rechaza antes de abrir fuentes y ejecuta el owner una sola vez."""

    selected_argv = tuple(sys.argv[1:] if argv is None else argv)
    dotenv_path = _parse_request(selected_argv)
    if dotenv_path is None:
        _emit(OAuthRefreshExecutionSnapshot(reason="oauth_refresh_owner_rejected"))
        return 2

    try:
        snapshot = asyncio.run(executor(dotenv_path=dotenv_path))
        if type(snapshot) is not OAuthRefreshExecutionSnapshot:
            raise TypeError("oauth_refresh_owner_result_invalid")
    except KeyboardInterrupt:
        snapshot = OAuthRefreshExecutionSnapshot(
            state="CANCELLED",
            reason="oauth_refresh_owner_cancelled",
            resources_closed=False,
        )
    except BaseException:
        snapshot = OAuthRefreshExecutionSnapshot(
            reason="oauth_refresh_owner_failed_safe",
            resources_closed=False,
        )

    _emit(snapshot)
    return {"READY": 0, "NO-GO": 1, "CANCELLED": 130}[snapshot.state]


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_OAUTH_REFRESH_TIMEOUT_SECONDS",
    "OAUTH_REFRESH_OWNER_COMMAND",
    "OAUTH_REFRESH_FUTURE_AUTHORIZATION",
    "OAUTH_REFRESH_OWNER_MODULE",
    "OAUTH_REFRESH_OWNER_READINESS",
    "OAUTH_REFRESH_REAL_CONFIRMATION",
    "OAuthRefreshExecutionSnapshot",
    "OAuthRefreshOwnerReadiness",
    "execute_protected_oauth_refresh_once",
    "main",
]
