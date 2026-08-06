"""Constructores concretos M76, limitados a transporte HTTP inyectado en memoria."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .bitrix_client import BitrixClient
from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_reply_rollback_contract import (
    ReplyRollbackDeletePreview,
    reply_delete_response_is_success,
)
from .nia_client import NiaClient


BITRIX_REPLY_DELETE_PATH = "/rest/imbot.v2.Chat.Message.delete"
MAX_DELETE_RESPONSE_BYTES = 64 * 1024


@dataclass(frozen=True)
class InMemoryConcreteBindingSettings:
    nia_base_url: str
    portal_url: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        if (
            not self.nia_base_url.strip()
            or not self.portal_url.strip()
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 10
        ):
            raise ValueError("m76_concrete_binding_settings_invalid")


@dataclass(frozen=True)
class InjectedInMemoryHttpResource:
    client: httpx.AsyncClient = field(repr=False)
    in_memory_only: bool = True
    external_calls: int = 0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.client, httpx.AsyncClient)
            or self.in_memory_only is not True
            or self.external_calls != 0
        ):
            raise ValueError("m76_http_resource_invalid")

    async def close(self) -> None:
        await self.client.aclose()


HttpResourceFactory = Callable[[str, float], InjectedInMemoryHttpResource]


class ExactReplyDeleteClient:
    """Cliente mínimo sin renovación, reintento ni ownership del HTTP inyectado."""

    def __init__(
        self,
        *,
        portal_url: str,
        access_token: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient,
    ) -> None:
        portal = portal_url.strip().rstrip("/")
        token = access_token.strip()
        if (
            not portal.startswith("https://")
            or not token
            or timeout_seconds <= 0
            or timeout_seconds > 10
            or not isinstance(http_client, httpx.AsyncClient)
        ):
            raise ValueError("m76_exact_delete_client_invalid")
        self._endpoint = f"{portal}{BITRIX_REPLY_DELETE_PATH}"
        self._access_token: Optional[str] = token
        self._http_client: Optional[httpx.AsyncClient] = http_client
        self._used = False

    def __repr__(self) -> str:
        return "ExactReplyDeleteClient(<redacted>)"

    async def delete_approved_reply(
        self, preview: ReplyRollbackDeletePreview
    ) -> object:
        if (
            self._used
            or self._http_client is None
            or self._access_token is None
            or not isinstance(preview, ReplyRollbackDeletePreview)
        ):
            self._used = True
            raise RuntimeError("m76_exact_delete_reuse_or_input_invalid")
        self._used = True
        payload = preview.model_dump(mode="json", exclude={"method"})
        payload["auth"] = self._access_token
        try:
            response = await self._http_client.post(self._endpoint, json=payload)
        except (httpx.TimeoutException, httpx.TransportError):
            return {}
        if (
            not 200 <= response.status_code <= 299
            or len(response.content) > MAX_DELETE_RESPONSE_BYTES
        ):
            return {}
        try:
            parsed = response.json()
        except ValueError:
            return {}
        return parsed if reply_delete_response_is_success(parsed) else {}

    async def close(self) -> None:
        self._access_token = None
        self._http_client = None


class _OwnedConcreteDependency:
    __slots__ = ("dependency", "_http", "attempted", "failed")

    def __init__(
        self, dependency: object, http_resource: InjectedInMemoryHttpResource
    ) -> None:
        self.dependency = dependency
        self._http: Optional[InjectedInMemoryHttpResource] = http_resource
        self.attempted = False
        self.failed = False

    async def close(self) -> None:
        if self.attempted:
            return
        self.attempted = True
        dependency, self.dependency = self.dependency, None
        http_resource, self._http = self._http, None
        try:
            method = getattr(dependency, "close", None)
            if callable(method):
                await method()
        except Exception:
            self.failed = True
        try:
            if http_resource is not None:
                await http_resource.close()
        except Exception:
            self.failed = True
        if self.failed:
            raise RuntimeError("m76_concrete_dependency_close_failed")


@dataclass(frozen=True)
class InMemoryConcreteBuiltDependency:
    dependency: object = field(repr=False)
    close_callback: object = field(repr=False)
    concrete_client_constructed: Literal[True] = True
    transport_in_memory_only: Literal[True] = True
    external_calls: Literal[0] = 0
    source_bound: Literal[False] = False

    def __post_init__(self) -> None:
        if self.dependency is None or not callable(self.close_callback):
            raise ValueError("m76_concrete_built_dependency_invalid")

    async def close(self) -> None:
        await self.close_callback()


class ConcreteBindingStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"


class ConcreteBindingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M76"] = "M76"
    status: ConcreteBindingStatus
    reason: Literal[
        "m76_four_concrete_clients_verified_in_memory",
        "m76_concrete_client_rehearsal_incomplete_or_close_failed",
    ]
    http_resource_factory_calls: int = Field(ge=0, le=4)
    nia_builder_calls: int = Field(ge=0, le=1)
    bitrix_builder_calls: int = Field(ge=0, le=1)
    deleter_builder_calls: int = Field(ge=0, le=1)
    history_builder_calls: int = Field(ge=0, le=1)
    close_calls: int = Field(ge=0, le=4)
    concrete_clients_constructed_in_memory: bool = False
    transport_in_memory_only: Literal[True] = True
    oauth_preloaded_token_only: Literal[True] = True
    oauth_refresh_surface_used: Literal[False] = False
    call_budget_per_client: Literal[1] = 1
    retry_budget: Literal[0] = 0
    maximum_timeout_seconds: Literal[10] = 10
    private_state_cleared: Literal[True] = True
    m75_connected: Literal[False] = False
    m73_connected: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class InMemoryConcreteBindingBuilders:
    """Construye cada cliente una vez; requiere HTTP explícitamente hermético."""

    _NAMES = ("nia", "bitrix", "deleter", "history")

    def __init__(
        self,
        *,
        settings: InMemoryConcreteBindingSettings,
        http_resource_factory: HttpResourceFactory,
    ) -> None:
        if (
            not isinstance(settings, InMemoryConcreteBindingSettings)
            or not callable(http_resource_factory)
        ):
            raise ValueError("m76_concrete_builders_invalid")
        self._settings: Optional[InMemoryConcreteBindingSettings] = settings
        self._http_resource_factory: Optional[HttpResourceFactory] = (
            http_resource_factory
        )
        self._used = {name: False for name in self._NAMES}
        self._build_calls = {name: 0 for name in self._NAMES}
        self._owned: list[_OwnedConcreteDependency] = []
        self._http_calls = 0
        self._closed = False
        self._terminal_failure = False

    def __repr__(self) -> str:
        return "InMemoryConcreteBindingBuilders(<redacted>)"

    def _prepare(self, name: str, timeout_seconds: float) -> InjectedInMemoryHttpResource:
        if (
            self._closed
            or self._settings is None
            or self._http_resource_factory is None
            or self._used[name]
            or timeout_seconds != self._settings.timeout_seconds
            or timeout_seconds <= 0
            or timeout_seconds > 10
        ):
            self._terminal_failure = True
            raise RuntimeError(f"m76_{name}_builder_rejected")
        self._used[name] = True
        self._build_calls[name] = 1
        self._http_calls += 1
        raw = self._http_resource_factory(name, timeout_seconds)
        if type(raw) is not InjectedInMemoryHttpResource:
            self._terminal_failure = True
            raise RuntimeError("m76_http_resource_factory_result_invalid")
        return raw

    def _wrap(
        self, dependency: object, http_resource: InjectedInMemoryHttpResource
    ) -> InMemoryConcreteBuiltDependency:
        owned = _OwnedConcreteDependency(dependency, http_resource)
        self._owned.append(owned)
        return InMemoryConcreteBuiltDependency(
            dependency=dependency,
            close_callback=owned.close,
        )

    async def build_nia(self, timeout_seconds: float) -> InMemoryConcreteBuiltDependency:
        http_resource = self._prepare("nia", timeout_seconds)
        assert self._settings is not None
        try:
            client = NiaClient(
                base_url=self._settings.nia_base_url,
                timeout_seconds=timeout_seconds,
                http_client=http_resource.client,
            )
        except Exception:
            self._terminal_failure = True
            await http_resource.close()
            raise
        return self._wrap(client, http_resource)

    async def build_bitrix(
        self, access_token: str, timeout_seconds: float
    ) -> InMemoryConcreteBuiltDependency:
        http_resource = self._prepare("bitrix", timeout_seconds)
        assert self._settings is not None
        try:
            client = BitrixClient(
                portal_url=self._settings.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                http_client=http_resource.client,
            )
        except Exception:
            self._terminal_failure = True
            await http_resource.close()
            raise
        return self._wrap(client, http_resource)

    async def build_deleter(
        self, access_token: str, timeout_seconds: float
    ) -> InMemoryConcreteBuiltDependency:
        http_resource = self._prepare("deleter", timeout_seconds)
        assert self._settings is not None
        try:
            client = ExactReplyDeleteClient(
                portal_url=self._settings.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                http_client=http_resource.client,
            )
        except Exception:
            self._terminal_failure = True
            await http_resource.close()
            raise
        return self._wrap(client, http_resource)

    async def build_history(
        self, access_token: str, timeout_seconds: float
    ) -> InMemoryConcreteBuiltDependency:
        http_resource = self._prepare("history", timeout_seconds)
        assert self._settings is not None
        try:
            client = BitrixHistoryR0Client(
                portal_url=self._settings.portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                http_client=http_resource.client,
            )
        except Exception:
            self._terminal_failure = True
            await http_resource.close()
            raise
        return self._wrap(client, http_resource)

    async def close(self) -> ConcreteBindingSnapshot:
        if not self._closed:
            self._closed = True
            for owned in reversed(self._owned):
                try:
                    await owned.close()
                except Exception:
                    self._terminal_failure = True
        closes = sum(item.attempted for item in self._owned)
        complete = (
            not self._terminal_failure
            and all(self._build_calls[name] == 1 for name in self._NAMES)
            and self._http_calls == 4
            and closes == 4
            and not any(item.failed for item in self._owned)
        )
        self._settings = None
        self._http_resource_factory = None
        self._owned.clear()
        return ConcreteBindingSnapshot(
            status=(ConcreteBindingStatus.VERIFIED if complete else ConcreteBindingStatus.NO_GO),
            reason=(
                "m76_four_concrete_clients_verified_in_memory"
                if complete
                else "m76_concrete_client_rehearsal_incomplete_or_close_failed"
            ),
            http_resource_factory_calls=self._http_calls,
            nia_builder_calls=self._build_calls["nia"],
            bitrix_builder_calls=self._build_calls["bitrix"],
            deleter_builder_calls=self._build_calls["deleter"],
            history_builder_calls=self._build_calls["history"],
            close_calls=closes,
            concrete_clients_constructed_in_memory=self._http_calls > 0,
        )


__all__ = [
    "BITRIX_REPLY_DELETE_PATH",
    "ConcreteBindingSnapshot",
    "ConcreteBindingStatus",
    "ExactReplyDeleteClient",
    "HttpResourceFactory",
    "InMemoryConcreteBindingBuilders",
    "InMemoryConcreteBindingSettings",
    "InMemoryConcreteBuiltDependency",
    "InjectedInMemoryHttpResource",
    "MAX_DELETE_RESPONSE_BYTES",
]
