"""Adaptador M48 one-shot sólo con dependencias inyectadas."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Optional, Protocol

from .bitrix_history_r0_client import BitrixHistoryReadResult
from .bitrix_history_r0_existing_diagnostic_owner import (
    ExistingHistoryDiagnosticResult,
    ExistingHistoryDiagnosticState,
    ExistingHistoryReaderFactoryError,
    execute_existing_history_diagnostic_once,
)
from .bitrix_history_r0_preflight_composition import (
    BitrixHistoryClientBuilder,
    StoredOAuthResources,
    StoredOAuthResourcesFactory,
    execute_stored_oauth_history_preflight_once,
)
from .config import ConnectorSettings


class InjectedExistingHistoryClient(Protocol):
    async def get_dialog(self, dialog_id: str) -> BitrixHistoryReadResult: ...
    async def get_session_history(self, session_id: int) -> BitrixHistoryReadResult: ...
    async def close(self) -> None: ...


InjectedHistoryClientBuilder = Callable[..., InjectedExistingHistoryClient]


class _OwnedExistingHistoryReader:
    """Cierra el cliente de historial y su recurso protegido independiente."""

    def __init__(
        self,
        client: InjectedExistingHistoryClient,
        resources: StoredOAuthResources,
    ) -> None:
        self._client = client
        self._resources = resources

    async def get_session_history(self, session_id: int) -> BitrixHistoryReadResult:
        return await self._client.get_session_history(session_id)

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


class InjectedExistingHistoryDiagnosticAdapter:
    """Consume como máximo una ejecución; no selecciona fuentes ni defaults reales."""

    __slots__ = (
        "_client_builder",
        "_history_resources_factory",
        "_preflight_resources_factory",
        "_settings",
        "_timeout_seconds",
        "_used",
    )

    def __init__(
        self,
        *,
        settings: ConnectorSettings,
        timeout_seconds: float,
        preflight_resources_factory: StoredOAuthResourcesFactory,
        history_resources_factory: StoredOAuthResourcesFactory,
        client_builder: InjectedHistoryClientBuilder,
    ) -> None:
        if (
            not callable(client_builder)
            or not callable(getattr(preflight_resources_factory, "build", None))
            or not callable(getattr(history_resources_factory, "build", None))
        ):
            raise TypeError("bitrix_history_existing_adapter_dependency_invalid")
        self._settings = settings
        self._timeout_seconds = timeout_seconds
        self._preflight_resources_factory = preflight_resources_factory
        self._history_resources_factory = history_resources_factory
        self._client_builder = client_builder
        self._used = False

    def __repr__(self) -> str:
        return "InjectedExistingHistoryDiagnosticAdapter(<redacted>)"

    async def __call__(self, *, execute: bool = False) -> ExistingHistoryDiagnosticResult:
        if not execute:
            return await execute_existing_history_diagnostic_once(
                execute=False,
                settings=self._settings,
                preflight_executor=self._unused_preflight,
                history_reader_factory=self._unused_history_factory,
            )
        if self._used:
            return ExistingHistoryDiagnosticResult(
                state=ExistingHistoryDiagnosticState.NO_GO,
                reason="bitrix_history_existing_adapter_already_used",
                failure_category="reader_other_safe_failure",
            )
        self._used = True

        async def preflight(settings: ConnectorSettings):
            return await execute_stored_oauth_history_preflight_once(
                settings=settings,
                timeout_seconds=self._timeout_seconds,
                resources_factory=self._preflight_resources_factory,
                client_builder=self._client_builder,
            )

        async def history_reader_factory() -> _OwnedExistingHistoryReader:
            resources: Optional[StoredOAuthResources] = None
            try:
                resources = await self._history_resources_factory.build(
                    self._settings,
                    timeout_seconds=self._timeout_seconds,
                )
                access_token = await resources.oauth_provider.get_access_token(
                    resources.member_id
                )
                client = self._client_builder(
                    portal_url=resources.portal_url,
                    access_token=access_token,
                    timeout_seconds=self._timeout_seconds,
                )
                reader = _OwnedExistingHistoryReader(client, resources)
                resources = None
                return reader
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
                    "bitrix_history_read_failed"
                    if resources_closed
                    else "bitrix_history_resources_close_failed"
                )
                raise ExistingHistoryReaderFactoryError(
                    reason,
                    resources_closed=resources_closed,
                ) from exc

        return await execute_existing_history_diagnostic_once(
            execute=True,
            settings=self._settings,
            preflight_executor=preflight,
            history_reader_factory=history_reader_factory,
        )

    async def _unused_preflight(self, _settings: ConnectorSettings):
        raise AssertionError("prepared adapter must not invoke preflight")

    async def _unused_history_factory(self):
        raise AssertionError("prepared adapter must not invoke history")


def compose_injected_existing_history_diagnostic_adapter(
    *,
    settings: ConnectorSettings,
    timeout_seconds: float,
    preflight_resources_factory: StoredOAuthResourcesFactory,
    history_resources_factory: StoredOAuthResourcesFactory,
    client_builder: InjectedHistoryClientBuilder,
) -> InjectedExistingHistoryDiagnosticAdapter:
    """Compone sólo dependencias explícitas; no abre ni consulta recursos."""

    return InjectedExistingHistoryDiagnosticAdapter(
        settings=settings,
        timeout_seconds=timeout_seconds,
        preflight_resources_factory=preflight_resources_factory,
        history_resources_factory=history_resources_factory,
        client_builder=client_builder,
    )


__all__ = [
    "InjectedExistingHistoryClient",
    "InjectedExistingHistoryDiagnosticAdapter",
    "InjectedHistoryClientBuilder",
    "compose_injected_existing_history_diagnostic_adapter",
]
