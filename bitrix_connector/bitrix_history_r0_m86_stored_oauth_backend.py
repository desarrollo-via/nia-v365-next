"""Primer subcorte M86: backend OAuth almacenado real-ready y one-shot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthRecord,
    MAX_INJECTED_STORED_OAUTH_BYTES,
)
from .config import ConnectorSettings
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


M86_STORED_OAUTH_TIMEOUT_SECONDS = 10.0


class M86StoredOAuthProvider(Protocol):
    async def get_access_token(self, member_id: str) -> str: ...


class M86StoredOAuthResources(Protocol):
    oauth_provider: M86StoredOAuthProvider
    member_id: str

    async def close(self) -> None: ...


class M86StoredOAuthResourcesFactory(Protocol):
    async def build(
        self,
        settings: ConnectorSettings,
        *,
        timeout_seconds: float,
    ) -> M86StoredOAuthResources: ...


class M86StoredOAuthBackend:
    """Adapta la fábrica real a M82 sin exponer capacidad de renovación."""

    __slots__ = (
        "_close_calls",
        "_closed",
        "_factory",
        "_load_calls",
        "_resources",
        "_token_read_calls",
        "_used",
    )

    def __init__(self, *, resources_factory: M86StoredOAuthResourcesFactory) -> None:
        if resources_factory is None or not callable(
            getattr(resources_factory, "build", None)
        ):
            raise TypeError("m86_stored_oauth_factory_invalid")
        self._factory: Optional[M86StoredOAuthResourcesFactory] = resources_factory
        self._resources: Optional[M86StoredOAuthResources] = None
        self._used = False
        self._closed = False
        self._load_calls = 0
        self._token_read_calls = 0
        self._close_calls = 0

    def __repr__(self) -> str:
        return "M86StoredOAuthBackend(<redacted>)"

    @property
    def load_calls(self) -> int:
        return self._load_calls

    @property
    def token_read_calls(self) -> int:
        return self._token_read_calls

    @property
    def close_calls(self) -> int:
        return self._close_calls

    async def load_stored_once(
        self,
        settings: ConnectorSettings,
    ) -> InjectedStoredOAuthRecord:
        factory = self._factory
        if self._used or self._closed or factory is None:
            self._used = True
            raise RuntimeError("m86_stored_oauth_backend_reuse_rejected")
        self._used = True
        self._load_calls = 1
        resources = await factory.build(
            settings,
            timeout_seconds=M86_STORED_OAUTH_TIMEOUT_SECONDS,
        )
        self._resources = resources
        provider = getattr(resources, "oauth_provider", None)
        member_id = getattr(resources, "member_id", None)
        if not callable(getattr(provider, "get_access_token", None)):
            raise TypeError("m86_stored_oauth_resources_invalid")
        if type(member_id) is not str or not member_id.strip():
            raise TypeError("m86_stored_oauth_resources_invalid")
        self._token_read_calls = 1
        token_text = await provider.get_access_token(member_id)
        if type(token_text) is not str:
            raise TypeError("m86_stored_oauth_token_invalid")
        token = bytearray(token_text.encode("utf-8"))
        token_text = ""
        if (
            not token
            or len(token) > MAX_INJECTED_STORED_OAUTH_BYTES
            or b"\x00" in token
        ):
            token[:] = b"\x00" * len(token)
            raise ValueError("m86_stored_oauth_token_invalid")
        return InjectedStoredOAuthRecord(access_token=token)

    async def close(self) -> None:
        resources, self._resources = self._resources, None
        self._factory = None
        if self._closed:
            return
        self._closed = True
        self._close_calls = 1
        if resources is not None:
            await resources.close()


def build_real_m86_stored_oauth_backend() -> M86StoredOAuthBackend:
    """Enlaza la fábrica productiva sin construir Mongo, OAuth ni red."""

    return M86StoredOAuthBackend(resources_factory=PilotDiscoveryOAuthFactory())


@dataclass(frozen=True)
class M86StoredOAuthBindingSnapshot:
    phase: Literal["M86-A"] = "M86-A"
    state: Literal["BOUND-NOT-OPENED"] = "BOUND-NOT-OPENED"
    stored_load_budget: Literal[1] = 1
    refresh_budget: Literal[0] = 0
    retry_budget: Literal[0] = 0
    cleanup_required: Literal[True] = True
    real_resource_builds: Literal[0] = 0
    real_token_reads: Literal[0] = 0
    source_opened: Literal[False] = False
    command_available: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    remaining_real_bindings: Literal[4] = 4


def inspect_m86_stored_oauth_binding() -> M86StoredOAuthBindingSnapshot:
    return M86StoredOAuthBindingSnapshot()


__all__ = [
    "M86StoredOAuthBackend",
    "M86StoredOAuthBindingSnapshot",
    "M86StoredOAuthProvider",
    "M86StoredOAuthResources",
    "M86StoredOAuthResourcesFactory",
    "M86_STORED_OAUTH_TIMEOUT_SECONDS",
    "build_real_m86_stored_oauth_backend",
    "inspect_m86_stored_oauth_binding",
]
