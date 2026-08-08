"""Segundo subcorte M86: fábrica HTTPS real-ready para cuatro clientes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal, Optional
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .bitrix_client import BitrixClient
from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_m76_in_memory_concrete_builders import (
    ExactReplyDeleteClient,
)
from .nia_client import NiaClient


M86_HTTPS_BINDING_NAMES = ("nia", "bitrix", "deleter", "history")
M86_HTTPS_TRANSPORT_NAMES = (
    *M86_HTTPS_BINDING_NAMES,
    "preflight_bot",
    "preflight_dialog",
    "roundtrip_history",
)
M86_HTTPS_TIMEOUT_SECONDS = 10.0


def _exact_https_origin(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("m86_https_origin_invalid")
    return candidate


@dataclass(frozen=True)
class M86HttpsClientSettings:
    nia_base_url: str
    portal_url: str
    timeout_seconds: float = M86_HTTPS_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "nia_base_url", _exact_https_origin(self.nia_base_url))
        object.__setattr__(self, "portal_url", _exact_https_origin(self.portal_url))
        if self.timeout_seconds <= 0 or self.timeout_seconds > M86_HTTPS_TIMEOUT_SECONDS:
            raise ValueError("m86_https_timeout_invalid")


AsyncClientFactory = Callable[[str, float], Awaitable[httpx.AsyncClient]]


async def build_real_m86_https_async_client(
    name: str,
    timeout_seconds: float,
) -> httpx.AsyncClient:
    if name not in M86_HTTPS_TRANSPORT_NAMES:
        raise ValueError("m86_https_binding_name_invalid")
    return httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=False,
    )


class _OwnedHttpsDependency:
    __slots__ = ("client", "dependency", "close_attempted", "close_failed")

    def __init__(self, dependency: object, client: httpx.AsyncClient) -> None:
        self.dependency: Optional[object] = dependency
        self.client: Optional[httpx.AsyncClient] = client
        self.close_attempted = False
        self.close_failed = False

    async def close(self) -> None:
        if self.close_attempted:
            return
        self.close_attempted = True
        dependency, self.dependency = self.dependency, None
        client, self.client = self.client, None
        first_error: Optional[BaseException] = None
        try:
            close_dependency = getattr(dependency, "close", None)
            if callable(close_dependency):
                await close_dependency()
        except BaseException as error:
            first_error = error
        try:
            if client is not None:
                await client.aclose()
        except BaseException as error:
            first_error = first_error or error
        if first_error is not None:
            self.close_failed = True
            raise RuntimeError("m86_https_dependency_close_failed") from first_error


@dataclass(frozen=True)
class M86BuiltHttpsDependency:
    dependency: object = field(repr=False)
    _owner: _OwnedHttpsDependency = field(repr=False)
    concrete_client_constructed: Literal[True] = True
    real_https_capable: Literal[True] = True
    external_calls: Literal[0] = 0

    async def close(self) -> None:
        await self._owner.close()


class M86HttpsFactorySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M86-B"] = "M86-B"
    status: Literal["VERIFIED", "NO-GO"]
    reason: Literal[
        "m86_four_real_https_clients_constructed_and_closed",
        "m86_real_https_factory_incomplete_or_close_failed",
    ]
    http_client_factory_calls: int = Field(ge=0, le=4)
    nia_builder_calls: int = Field(ge=0, le=1)
    bitrix_builder_calls: int = Field(ge=0, le=1)
    deleter_builder_calls: int = Field(ge=0, le=1)
    history_builder_calls: int = Field(ge=0, le=1)
    dependency_close_calls: int = Field(ge=0, le=4)
    http_close_calls: int = Field(ge=0, le=4)
    concrete_clients_constructed: int = Field(ge=0, le=4)
    retry_budget: Literal[0] = 0
    maximum_timeout_seconds: Literal[10] = 10
    requests_executed: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False


class M86RealHttpsClientFactory:
    """Construye cada cliente una vez y conserva ownership de su HTTP."""

    __slots__ = (
        "_build_calls",
        "_closed",
        "_http_client_factory",
        "_http_factory_calls",
        "_owned",
        "_settings",
        "_terminal_failure",
        "_used",
    )

    def __init__(
        self,
        *,
        settings: M86HttpsClientSettings,
        http_client_factory: AsyncClientFactory = build_real_m86_https_async_client,
    ) -> None:
        if not isinstance(settings, M86HttpsClientSettings) or not callable(
            http_client_factory
        ):
            raise TypeError("m86_https_factory_dependency_invalid")
        self._settings: Optional[M86HttpsClientSettings] = settings
        self._http_client_factory: Optional[AsyncClientFactory] = http_client_factory
        self._used = {name: False for name in M86_HTTPS_BINDING_NAMES}
        self._build_calls = {name: 0 for name in M86_HTTPS_BINDING_NAMES}
        self._http_factory_calls = 0
        self._owned: list[_OwnedHttpsDependency] = []
        self._closed = False
        self._terminal_failure = False

    def __repr__(self) -> str:
        return "M86RealHttpsClientFactory(<redacted>)"

    async def _prepare(self, name: str, timeout_seconds: float) -> httpx.AsyncClient:
        settings = self._settings
        client_factory = self._http_client_factory
        if (
            self._closed
            or self._terminal_failure
            or settings is None
            or client_factory is None
            or name not in M86_HTTPS_BINDING_NAMES
            or self._used[name]
            or timeout_seconds != settings.timeout_seconds
        ):
            self._terminal_failure = True
            raise RuntimeError(f"m86_{name}_https_builder_rejected")
        self._used[name] = True
        self._build_calls[name] = 1
        self._http_factory_calls += 1
        try:
            client = await client_factory(name, timeout_seconds)
        except BaseException:
            self._terminal_failure = True
            raise
        if not isinstance(client, httpx.AsyncClient):
            self._terminal_failure = True
            raise TypeError("m86_https_client_factory_result_invalid")
        return client

    async def _wrap(self, dependency: object, client: httpx.AsyncClient) -> M86BuiltHttpsDependency:
        owner = _OwnedHttpsDependency(dependency, client)
        self._owned.append(owner)
        return M86BuiltHttpsDependency(dependency=dependency, _owner=owner)

    async def build_nia(self, timeout_seconds: float) -> M86BuiltHttpsDependency:
        client = await self._prepare("nia", timeout_seconds)
        assert self._settings is not None
        try:
            dependency = NiaClient(
                base_url=self._settings.nia_base_url,
                timeout_seconds=timeout_seconds,
                http_client=client,
            )
        except BaseException:
            self._terminal_failure = True
            await client.aclose()
            raise
        return await self._wrap(dependency, client)

    async def build_bitrix(
        self, access_token: str, timeout_seconds: float
    ) -> M86BuiltHttpsDependency:
        client = await self._prepare("bitrix", timeout_seconds)
        assert self._settings is not None
        try:
            dependency = BitrixClient(
                portal_url=self._settings.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                http_client=client,
            )
        except BaseException:
            self._terminal_failure = True
            await client.aclose()
            raise
        return await self._wrap(dependency, client)

    async def build_deleter(
        self, access_token: str, timeout_seconds: float
    ) -> M86BuiltHttpsDependency:
        client = await self._prepare("deleter", timeout_seconds)
        assert self._settings is not None
        try:
            dependency = ExactReplyDeleteClient(
                portal_url=self._settings.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                http_client=client,
            )
        except BaseException:
            self._terminal_failure = True
            await client.aclose()
            raise
        return await self._wrap(dependency, client)

    async def build_history(
        self, access_token: str, timeout_seconds: float
    ) -> M86BuiltHttpsDependency:
        client = await self._prepare("history", timeout_seconds)
        assert self._settings is not None
        try:
            dependency = BitrixHistoryR0Client(
                portal_url=self._settings.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                http_client=client,
            )
        except BaseException:
            self._terminal_failure = True
            await client.aclose()
            raise
        return await self._wrap(dependency, client)

    async def close(self) -> M86HttpsFactorySnapshot:
        if not self._closed:
            self._closed = True
            for owner in reversed(self._owned):
                try:
                    await owner.close()
                except BaseException:
                    self._terminal_failure = True
        close_calls = sum(owner.close_attempted for owner in self._owned)
        http_close_calls = sum(owner.close_attempted for owner in self._owned)
        complete = (
            not self._terminal_failure
            and all(self._build_calls[name] == 1 for name in M86_HTTPS_BINDING_NAMES)
            and self._http_factory_calls == 4
            and close_calls == 4
            and not any(owner.close_failed for owner in self._owned)
        )
        snapshot = M86HttpsFactorySnapshot(
            status="VERIFIED" if complete else "NO-GO",
            reason=(
                "m86_four_real_https_clients_constructed_and_closed"
                if complete
                else "m86_real_https_factory_incomplete_or_close_failed"
            ),
            http_client_factory_calls=self._http_factory_calls,
            nia_builder_calls=self._build_calls["nia"],
            bitrix_builder_calls=self._build_calls["bitrix"],
            deleter_builder_calls=self._build_calls["deleter"],
            history_builder_calls=self._build_calls["history"],
            dependency_close_calls=close_calls,
            http_close_calls=http_close_calls,
            concrete_clients_constructed=len(self._owned),
        )
        self._settings = None
        self._http_client_factory = None
        self._owned.clear()
        return snapshot


def build_real_m86_https_client_factory(
    *,
    nia_base_url: str,
    portal_url: str,
) -> M86RealHttpsClientFactory:
    """Enlaza transporte HTTPS real sin construir clientes ni abrir red."""

    return M86RealHttpsClientFactory(
        settings=M86HttpsClientSettings(
            nia_base_url=nia_base_url,
            portal_url=portal_url,
        )
    )


@dataclass(frozen=True)
class M86HttpsBindingSnapshot:
    phase: Literal["M86-B"] = "M86-B"
    state: Literal["BOUND-NOT-OPENED"] = "BOUND-NOT-OPENED"
    binding_names: tuple[str, str, str, str] = M86_HTTPS_BINDING_NAMES
    client_budget: Literal[4] = 4
    request_budget_before_confirmation: Literal[0] = 0
    retry_budget: Literal[0] = 0
    real_clients_constructed: Literal[0] = 0
    real_requests_executed: Literal[0] = 0
    resources_opened: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    command_available: Literal[False] = False
    remaining_real_bindings: Literal[3] = 3


def inspect_m86_https_binding() -> M86HttpsBindingSnapshot:
    return M86HttpsBindingSnapshot()


__all__ = [
    "AsyncClientFactory",
    "M86BuiltHttpsDependency",
    "M86HttpsBindingSnapshot",
    "M86HttpsClientSettings",
    "M86HttpsFactorySnapshot",
    "M86RealHttpsClientFactory",
    "M86_HTTPS_BINDING_NAMES",
    "M86_HTTPS_TRANSPORT_NAMES",
    "M86_HTTPS_TIMEOUT_SECONDS",
    "build_real_m86_https_client_factory",
    "build_real_m86_https_async_client",
    "inspect_m86_https_binding",
]
