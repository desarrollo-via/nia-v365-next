"""Bindings M75 dormidos, ejercitables sólo mediante builders inyectados."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_client import (
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from .bitrix_history_r0_m70_sender_factory_composition import (
    InjectedFixtureSenderResource,
)
from .bitrix_history_r0_m71_rollback_factory_composition import (
    InjectedFixtureRollbackResource,
)
from .bitrix_history_r0_m76_in_memory_concrete_builders import (
    InMemoryConcreteBuiltDependency,
)
from .bitrix_history_r0_m77_protected_resources import (
    InjectedSealedInMemoryRollbackResource,
    InjectedSealedInMemorySenderResource,
    ProtectedBindingClass,
)


CloseCallback = Callable[[], Awaitable[None]]
OAuthLoader = Callable[[], Awaitable["InjectedFixtureStoredOAuthResource"]]
NiaBuilder = Callable[[float], Awaitable[object]]
BitrixBuilder = Callable[[str, float], Awaitable[object]]


@dataclass(frozen=True)
class InjectedFixtureStoredOAuthResource:
    access_token: str = field(repr=False)
    close_callback: CloseCallback = field(repr=False)
    fixture_only: bool = True
    real_oauth_loaded: bool = False
    refresh_calls: int = 0

    def __post_init__(self) -> None:
        if (
            not self.access_token.strip()
            or not callable(self.close_callback)
            or self.fixture_only is not True
            or self.real_oauth_loaded is not False
            or self.refresh_calls != 0
        ):
            raise ValueError("m75_fixture_oauth_resource_invalid")

    async def close(self) -> None:
        await self.close_callback()


@dataclass(frozen=True)
class InjectedFixtureBuiltDependency:
    dependency: object
    close_callback: CloseCallback = field(repr=False)
    fixture_only: bool = True
    real_client_constructed: bool = False
    external_calls: int = 0

    def __post_init__(self) -> None:
        if (
            self.dependency is None
            or not callable(self.close_callback)
            or self.fixture_only is not True
            or self.real_client_constructed is not False
            or self.external_calls != 0
        ):
            raise ValueError("m75_fixture_built_dependency_invalid")


BuiltDependency = InjectedFixtureBuiltDependency | InMemoryConcreteBuiltDependency


class _TrackedClose:
    __slots__ = ("_callback", "attempted", "failed")

    def __init__(self, callback: CloseCallback) -> None:
        self._callback: Optional[CloseCallback] = callback
        self.attempted = False
        self.failed = False

    async def close(self) -> None:
        if self.attempted:
            return
        self.attempted = True
        callback, self._callback = self._callback, None
        try:
            if callback is not None:
                await callback()
        except Exception:
            self.failed = True
            raise
        finally:
            callback = None


class _TypedPostDeleteHistoryAdapter:
    __slots__ = ("_dependency", "_used")

    def __init__(self, dependency: object) -> None:
        self._dependency: Optional[object] = dependency
        self._used = False

    async def read_post_delete_history(self, *, session_id: int) -> object:
        if self._used or self._dependency is None or session_id <= 0:
            self._dependency = None
            raise RuntimeError("m75_post_delete_reader_reuse_or_input_invalid")
        self._used = True
        dependency, self._dependency = self._dependency, None
        method = getattr(dependency, "get_session_history", None)
        if not callable(method):
            raise RuntimeError("m75_typed_history_candidate_invalid")
        result = await method(session_id)
        if (
            not isinstance(result, BitrixHistoryReadResult)
            or result.decision is not BitrixHistoryReadDecision.SUCCESS
            or result.history is None
        ):
            raise RuntimeError("m75_typed_history_result_invalid")
        history = result.history
        return {
            "result": {
                "chatId": history.chat_id,
                "sessionId": history.session_id,
                "message": {
                    str(message.id): {"id": message.id}
                    for message in history.messages
                },
            }
        }


class DormantBindingStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"


class DormantBindingSnapshot(BaseModel):
    """Evidencia M75 redactada; no contiene token, payload o dependencia."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M75"] = "M75"
    status: DormantBindingStatus
    reason: Literal[
        "m75_four_fixture_bindings_rehearsed_and_closed",
        "m75_four_sealed_in_memory_bindings_rehearsed_and_closed",
        "m75_binding_rehearsal_incomplete_or_close_failed",
    ]
    oauth_loader_calls: int = Field(ge=0, le=1)
    oauth_refresh_calls: Literal[0] = 0
    oauth_close_calls: int = Field(ge=0, le=1)
    nia_builder_calls: int = Field(ge=0, le=1)
    bitrix_builder_calls: int = Field(ge=0, le=1)
    deleter_builder_calls: int = Field(ge=0, le=1)
    history_builder_calls: int = Field(ge=0, le=1)
    dependency_close_calls: int = Field(ge=0, le=4)
    call_budget_per_binding: Literal[1] = 1
    retry_budget: Literal[0] = 0
    maximum_timeout_seconds: Literal[10] = 10
    shared_oauth_owner: Literal[True] = True
    typed_history_shape_adapted: Literal[True] = True
    private_state_cleared: Literal[True] = True
    binding_class: Literal[
        "fixture-double", "sealed-in-memory-concrete"
    ] = "fixture-double"
    fixture_only: bool = True
    concrete_clients_constructed_in_memory: bool = False
    network_capable_resources_accepted: Literal[False] = False
    real_oauth_loaded: Literal[False] = False
    real_clients_constructed: Literal[False] = False
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


class DormantRealBindingOwner:
    """Owner perezoso one-shot; no conoce configuración ni builders reales."""

    _NAMES = ("nia", "bitrix", "deleter", "history")

    def __init__(
        self,
        *,
        oauth_loader: OAuthLoader,
        nia_builder: NiaBuilder,
        bitrix_builder: BitrixBuilder,
        deleter_builder: BitrixBuilder,
        history_builder: BitrixBuilder,
        timeout_seconds: float,
    ) -> None:
        dependencies = (
            oauth_loader,
            nia_builder,
            bitrix_builder,
            deleter_builder,
            history_builder,
        )
        if (
            any(not callable(item) for item in dependencies)
            or timeout_seconds <= 0
            or timeout_seconds > 10
        ):
            raise ValueError("m75_dormant_binding_owner_invalid")
        self._oauth_loader: Optional[OAuthLoader] = oauth_loader
        self._builders: dict[str, Optional[Callable[..., Awaitable[object]]]] = {
            "nia": nia_builder,
            "bitrix": bitrix_builder,
            "deleter": deleter_builder,
            "history": history_builder,
        }
        self._timeout_seconds = timeout_seconds
        self._oauth_resource: Optional[InjectedFixtureStoredOAuthResource] = None
        self._access_token: Optional[str] = None
        self._oauth_close: Optional[_TrackedClose] = None
        self._tracked: list[_TrackedClose] = []
        self._builder_calls = {name: 0 for name in self._NAMES}
        self.oauth_loader_calls = 0
        self._closed = False
        self._terminal_failure = False
        self._binding_class: Optional[ProtectedBindingClass] = None

    def __repr__(self) -> str:
        return "DormantRealBindingOwner(<redacted>)"

    async def _token_once(self) -> str:
        if self._access_token is not None:
            return self._access_token
        loader, self._oauth_loader = self._oauth_loader, None
        if loader is None:
            self._terminal_failure = True
            raise RuntimeError("m75_oauth_reuse_rejected")
        self.oauth_loader_calls = 1
        raw = await loader()
        if type(raw) is not InjectedFixtureStoredOAuthResource:
            self._terminal_failure = True
            raise RuntimeError("m75_oauth_resource_invalid")
        self._oauth_resource = raw
        self._oauth_close = _TrackedClose(raw.close)
        self._access_token = raw.access_token
        return self._access_token

    async def _build(self, name: str, *, oauth: bool) -> BuiltDependency:
        if self._closed:
            raise RuntimeError("m75_owner_closed")
        builder = self._builders.get(name)
        self._builders[name] = None
        if builder is None:
            self._terminal_failure = True
            raise RuntimeError(f"m75_{name}_factory_reuse_rejected")
        self._builder_calls[name] = 1
        try:
            if oauth:
                raw = await builder(await self._token_once(), self._timeout_seconds)
            else:
                raw = await builder(self._timeout_seconds)
        except BaseException:
            self._terminal_failure = True
            raise
        if type(raw) not in (
            InjectedFixtureBuiltDependency,
            InMemoryConcreteBuiltDependency,
        ):
            self._terminal_failure = True
            raise RuntimeError(f"m75_{name}_builder_result_invalid")
        binding_class = (
            ProtectedBindingClass.FIXTURE_DOUBLE
            if type(raw) is InjectedFixtureBuiltDependency
            else ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
        )
        if self._binding_class is None:
            self._binding_class = binding_class
        elif self._binding_class is not binding_class:
            self._terminal_failure = True
            try:
                await raw.close_callback()
            except Exception:
                pass
            raise RuntimeError("m75_mixed_binding_classes_rejected")
        return raw

    def _track(self, raw: BuiltDependency) -> _TrackedClose:
        tracked = _TrackedClose(raw.close_callback)
        self._tracked.append(tracked)
        return tracked

    async def build_nia_sender_once(self) -> object:
        raw = await self._build("nia", oauth=False)
        if type(raw) is InMemoryConcreteBuiltDependency:
            return InjectedSealedInMemorySenderResource(
                sender=raw.dependency,
                close_callback=self._track(raw).close,
            )
        return InjectedFixtureSenderResource(
            sender=raw.dependency,
            close_callback=self._track(raw).close,
        )

    async def build_bitrix_sender_once(self) -> object:
        raw = await self._build("bitrix", oauth=True)
        if type(raw) is InMemoryConcreteBuiltDependency:
            return InjectedSealedInMemorySenderResource(
                sender=raw.dependency,
                close_callback=self._track(raw).close,
            )
        return InjectedFixtureSenderResource(
            sender=raw.dependency,
            close_callback=self._track(raw).close,
        )

    async def build_deleter_once(self) -> object:
        raw = await self._build("deleter", oauth=True)
        if type(raw) is InMemoryConcreteBuiltDependency:
            return InjectedSealedInMemoryRollbackResource(
                dependency=raw.dependency,
                close_callback=self._track(raw).close,
            )
        return InjectedFixtureRollbackResource(
            dependency=raw.dependency,
            close_callback=self._track(raw).close,
        )

    async def build_post_delete_reader_once(self) -> object:
        raw = await self._build("history", oauth=True)
        if type(raw) is InMemoryConcreteBuiltDependency:
            return InjectedSealedInMemoryRollbackResource(
                dependency=_TypedPostDeleteHistoryAdapter(raw.dependency),
                close_callback=self._track(raw).close,
            )
        return InjectedFixtureRollbackResource(
            dependency=_TypedPostDeleteHistoryAdapter(raw.dependency),
            close_callback=self._track(raw).close,
        )

    async def close(self) -> DormantBindingSnapshot:
        if not self._closed:
            self._closed = True
            for tracked in reversed(self._tracked):
                try:
                    await tracked.close()
                except Exception:
                    self._terminal_failure = True
            if self._oauth_close is not None:
                try:
                    await self._oauth_close.close()
                except Exception:
                    self._terminal_failure = True
        dependency_closes = sum(item.attempted for item in self._tracked)
        oauth_closes = int(self._oauth_close is not None and self._oauth_close.attempted)
        complete = (
            not self._terminal_failure
            and not any(item.failed for item in self._tracked)
            and not (self._oauth_close is not None and self._oauth_close.failed)
            and all(self._builder_calls[name] == 1 for name in self._NAMES)
            and dependency_closes == 4
            and self.oauth_loader_calls == 1
            and oauth_closes == 1
        )
        binding_class = self._binding_class or ProtectedBindingClass.FIXTURE_DOUBLE
        self._oauth_loader = None
        self._builders.clear()
        self._oauth_resource = None
        self._access_token = None
        self._timeout_seconds = 0
        return DormantBindingSnapshot(
            status=(DormantBindingStatus.VERIFIED if complete else DormantBindingStatus.NO_GO),
            reason=(
                (
                    "m75_four_sealed_in_memory_bindings_rehearsed_and_closed"
                    if binding_class
                    is ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
                    else "m75_four_fixture_bindings_rehearsed_and_closed"
                )
                if complete
                else "m75_binding_rehearsal_incomplete_or_close_failed"
            ),
            oauth_loader_calls=self.oauth_loader_calls,
            oauth_close_calls=oauth_closes,
            nia_builder_calls=self._builder_calls.get("nia", 0),
            bitrix_builder_calls=self._builder_calls.get("bitrix", 0),
            deleter_builder_calls=self._builder_calls.get("deleter", 0),
            history_builder_calls=self._builder_calls.get("history", 0),
            dependency_close_calls=dependency_closes,
            binding_class=binding_class.value,
            fixture_only=binding_class is ProtectedBindingClass.FIXTURE_DOUBLE,
            concrete_clients_constructed_in_memory=(
                binding_class
                is ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            ),
        )


__all__ = [
    "BitrixBuilder",
    "DormantBindingSnapshot",
    "DormantBindingStatus",
    "DormantRealBindingOwner",
    "InjectedFixtureBuiltDependency",
    "InjectedFixtureStoredOAuthResource",
    "NiaBuilder",
    "OAuthLoader",
]
