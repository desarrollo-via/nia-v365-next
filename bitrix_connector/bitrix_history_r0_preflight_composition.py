"""Composición protegida del OAuth almacenado para el preflight R0."""

from __future__ import annotations

import asyncio
from typing import Callable, Optional, Protocol

from .bitrix_history_r0_client import BitrixHistoryR0Client, BitrixHistoryReadResult
from .bitrix_history_r0_preflight import (
    BitrixHistoryPreflightFactoryError,
    BitrixHistoryPreflightReader,
    BitrixHistoryR0PreflightOutcome,
    execute_bitrix_history_r0_preflight_once,
)
from .bitrix_history_r0_runner import BitrixHistoryR0Result, BitrixHistoryR0Status
from .config import ConnectorSettings
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 10.0


class StoredOAuthProvider(Protocol):
    async def get_access_token(self, member_id: str) -> str: ...


class StoredOAuthResources(Protocol):
    oauth_provider: StoredOAuthProvider
    portal_url: str
    member_id: str

    async def close(self) -> None: ...


class StoredOAuthResourcesFactory(Protocol):
    async def build(
        self,
        settings: ConnectorSettings,
        *,
        timeout_seconds: float,
    ) -> StoredOAuthResources: ...


BitrixHistoryClientBuilder = Callable[..., BitrixHistoryPreflightReader]


class _OwnedPreflightReader:
    """Cierra el cliente de lectura y todos los recursos OAuth/Mongo."""

    def __init__(
        self,
        client: BitrixHistoryPreflightReader,
        resources: StoredOAuthResources,
    ) -> None:
        self._client = client
        self._resources = resources

    async def get_dialog(self, dialog_id: str) -> BitrixHistoryReadResult:
        return await self._client.get_dialog(dialog_id)

    async def close(self) -> None:
        first_error: Optional[BaseException] = None
        try:
            await self._client.close()
        except BaseException as exc:
            first_error = exc
        try:
            await self._resources.close()
        except BaseException as exc:
            first_error = first_error or exc
        if first_error is not None:
            raise first_error


def _blocked(reason: str) -> BitrixHistoryR0PreflightOutcome:
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.NO_GO,
            reason=reason,
            dialog_read_calls=0,
            history_read_calls=0,
            resources_closed=True,
        )
    )


async def execute_stored_oauth_history_preflight_once(
    *,
    settings: ConnectorSettings,
    timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    resources_factory: Optional[StoredOAuthResourcesFactory] = None,
    client_builder: BitrixHistoryClientBuilder = BitrixHistoryR0Client,
) -> BitrixHistoryR0PreflightOutcome:
    """Obtiene un token almacenado una vez y delega la única lectura aprobada."""

    if timeout_seconds <= 0 or timeout_seconds > DEFAULT_PREFLIGHT_TIMEOUT_SECONDS:
        return _blocked("bitrix_history_timeout_invalid")
    selected_factory: StoredOAuthResourcesFactory = (
        resources_factory or PilotDiscoveryOAuthFactory()
    )

    async def build_owned_client() -> BitrixHistoryPreflightReader:
        resources: Optional[StoredOAuthResources] = None
        try:
            resources = await selected_factory.build(
                settings,
                timeout_seconds=timeout_seconds,
            )
            access_token = await resources.oauth_provider.get_access_token(
                resources.member_id
            )
            client = client_builder(
                portal_url=resources.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            )
            return _OwnedPreflightReader(client, resources)
        except asyncio.CancelledError:
            if resources is not None:
                await resources.close()
            raise
        except Exception as exc:
            resources_closed = True
            if resources is not None:
                try:
                    await resources.close()
                except Exception:
                    resources_closed = False
            reason = (
                "bitrix_history_preflight_failed_safe"
                if resources_closed
                else "bitrix_history_resources_close_failed"
            )
            raise BitrixHistoryPreflightFactoryError(
                reason,
                resources_closed=resources_closed,
            ) from exc

    return await execute_bitrix_history_r0_preflight_once(
        client_factory=build_owned_client,
        settings=settings,
    )


__all__ = [
    "DEFAULT_PREFLIGHT_TIMEOUT_SECONDS",
    "BitrixHistoryClientBuilder",
    "StoredOAuthProvider",
    "StoredOAuthResources",
    "StoredOAuthResourcesFactory",
    "execute_stored_oauth_history_preflight_once",
]
