"""Owner M83: M82 y cuatro clientes HTTPS concretos, sólo sobre MockTransport."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Literal, Optional
from urllib.parse import urlsplit

import httpx

from .bitrix_history_r0_m75_dormant_real_bindings import (
    DormantBindingSnapshot,
    DormantBindingStatus,
    DormantRealBindingOwner,
    InjectedFixtureStoredOAuthResource,
)
from .bitrix_history_r0_m76_in_memory_concrete_builders import (
    ConcreteBindingSnapshot,
    ConcreteBindingStatus,
    InMemoryConcreteBindingBuilders,
    InMemoryConcreteBindingSettings,
    InjectedInMemoryHttpResource,
)
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
)
from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthBackend,
    M82CompositionSnapshot,
    M82Status,
    StoredOAuthAccessView,
    execute_m82_injected_settings_oauth_once,
)
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
)
from .config import ConnectorSettings, load_settings


MockTransportFactory = Callable[[str], httpx.MockTransport]
_BINDING_NAMES = ("nia", "bitrix", "deleter", "history")


def _exact_https_origin(raw: str, *, allow_bare_host: bool) -> str:
    candidate = raw.strip().rstrip("/")
    if allow_bare_host and "://" not in candidate:
        candidate = f"https://{candidate}"
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
        raise ValueError("m83_exact_https_origin_invalid")
    return candidate


class M83Status(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class M83HttpsOwnerSnapshot:
    phase: Literal["M83"]
    status: M83Status
    reason: str
    owner_run_calls: int
    credential_source_read_calls: int
    settings_load_calls: int
    oauth_load_calls: int
    oauth_refresh_calls: Literal[0]
    oauth_token_view_reads: int
    oauth_close_calls: int
    oauth_close_verified: bool
    binding_oauth_loader_calls: int
    binding_oauth_close_calls: int
    http_resource_factory_calls: int
    concrete_builder_calls: int
    dependency_close_calls: int
    http_close_calls: int
    https_origins_verified: bool
    same_private_token_shared: bool
    construction_lazy_until_m82_operation: bool
    all_private_resources_closed: bool
    retry_budget: Literal[0] = 0
    maximum_timeout_seconds: Literal[10] = 10
    transport_kind: Literal["httpx.MockTransport"] = "httpx.MockTransport"
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False


class M83InjectedHttpsOwner:
    """Owner one-shot sin defaults de red, fuente real, comando o reintento."""

    __slots__ = (
        "_credential_backend",
        "_mock_transport_factory",
        "_nia_base_url",
        "_oauth_backend",
        "_settings_loader",
        "_used",
    )

    def __init__(
        self,
        *,
        credential_backend: InjectedWindowsCredentialBackend,
        oauth_backend: InjectedStoredOAuthBackend,
        nia_base_url: str,
        mock_transport_factory: MockTransportFactory,
        settings_loader: ProtectedSettingsLoader = load_settings,
    ) -> None:
        if (
            credential_backend is None
            or oauth_backend is None
            or not callable(mock_transport_factory)
            or not callable(settings_loader)
        ):
            raise TypeError("m83_owner_dependency_invalid")
        self._credential_backend: Optional[InjectedWindowsCredentialBackend] = (
            credential_backend
        )
        self._oauth_backend: Optional[InjectedStoredOAuthBackend] = oauth_backend
        self._nia_base_url = _exact_https_origin(
            nia_base_url, allow_bare_host=False
        )
        self._mock_transport_factory: Optional[MockTransportFactory] = (
            mock_transport_factory
        )
        self._settings_loader: Optional[ProtectedSettingsLoader] = settings_loader
        self._used = False

    def __repr__(self) -> str:
        return "M83InjectedHttpsOwner(<redacted>)"

    @staticmethod
    def _empty_snapshot(*, reason: str) -> M83HttpsOwnerSnapshot:
        return M83HttpsOwnerSnapshot(
            phase="M83",
            status=M83Status.NO_GO,
            reason=reason,
            owner_run_calls=0,
            credential_source_read_calls=0,
            settings_load_calls=0,
            oauth_load_calls=0,
            oauth_refresh_calls=0,
            oauth_token_view_reads=0,
            oauth_close_calls=0,
            oauth_close_verified=False,
            binding_oauth_loader_calls=0,
            binding_oauth_close_calls=0,
            http_resource_factory_calls=0,
            concrete_builder_calls=0,
            dependency_close_calls=0,
            http_close_calls=0,
            https_origins_verified=False,
            same_private_token_shared=False,
            construction_lazy_until_m82_operation=True,
            all_private_resources_closed=False,
        )

    async def run_once(self) -> M83HttpsOwnerSnapshot:
        if self._used:
            return self._empty_snapshot(reason="m83_owner_reuse_rejected")
        self._used = True
        credential_backend, self._credential_backend = self._credential_backend, None
        oauth_backend, self._oauth_backend = self._oauth_backend, None
        transport_factory, self._mock_transport_factory = (
            self._mock_transport_factory,
            None,
        )
        settings_loader, self._settings_loader = self._settings_loader, None
        nia_base_url, self._nia_base_url = self._nia_base_url, ""
        if (
            credential_backend is None
            or oauth_backend is None
            or transport_factory is None
            or settings_loader is None
        ):
            return self._empty_snapshot(reason="m83_owner_dependencies_consumed")

        binding_snapshot: DormantBindingSnapshot | None = None
        concrete_snapshot: ConcreteBindingSnapshot | None = None
        binding_oauth_close_calls = 0
        https_verified = False
        same_token_shared = False

        async def operation(
            settings: ConnectorSettings, token_view: StoredOAuthAccessView
        ) -> None:
            nonlocal binding_oauth_close_calls
            nonlocal binding_snapshot, concrete_snapshot
            nonlocal https_verified, same_token_shared
            if not settings.bitrix_domain:
                raise ValueError("m83_bitrix_domain_missing")
            portal_url = _exact_https_origin(
                settings.bitrix_domain, allow_bare_host=True
            )
            https_verified = True

            transport_names: list[str] = []

            def http_resource_factory(
                name: str, timeout_seconds: float
            ) -> InjectedInMemoryHttpResource:
                if name not in _BINDING_NAMES or name in transport_names:
                    raise RuntimeError("m83_mock_transport_name_invalid")
                transport = transport_factory(name)
                if type(transport) is not httpx.MockTransport:
                    raise TypeError("m83_mock_transport_required")
                transport_names.append(name)
                return InjectedInMemoryHttpResource(
                    client=httpx.AsyncClient(
                        transport=transport,
                        timeout=timeout_seconds,
                    )
                )

            concrete = InMemoryConcreteBindingBuilders(
                settings=InMemoryConcreteBindingSettings(
                    nia_base_url=nia_base_url,
                    portal_url=portal_url,
                    timeout_seconds=10,
                ),
                http_resource_factory=http_resource_factory,
            )

            async def close_binding_oauth() -> None:
                nonlocal binding_oauth_close_calls
                binding_oauth_close_calls += 1

            async def load_binding_oauth() -> InjectedFixtureStoredOAuthResource:
                nonlocal same_token_shared
                token = token_view.read_text()
                same_token_shared = True
                return InjectedFixtureStoredOAuthResource(
                    access_token=token,
                    close_callback=close_binding_oauth,
                )

            binding = DormantRealBindingOwner(
                oauth_loader=load_binding_oauth,
                nia_builder=concrete.build_nia,
                bitrix_builder=concrete.build_bitrix,
                deleter_builder=concrete.build_deleter,
                history_builder=concrete.build_history,
                timeout_seconds=10,
            )
            try:
                await binding.build_nia_sender_once()
                await binding.build_bitrix_sender_once()
                await binding.build_deleter_once()
                await binding.build_post_delete_reader_once()
                if tuple(transport_names) != _BINDING_NAMES:
                    raise RuntimeError("m83_four_lazy_factories_incomplete")
            finally:
                binding_snapshot = await binding.close()
                concrete_snapshot = await concrete.close()

        try:
            m82 = await execute_m82_injected_settings_oauth_once(
                credential_backend=credential_backend,
                oauth_backend=oauth_backend,
                operation=operation,
                settings_loader=settings_loader,
            )
        except asyncio.CancelledError:
            m82 = M82CompositionSnapshot(
                phase="M82",
                status=M82Status.CANCELLED,
                reason="m82_injected_settings_oauth_cancelled",
                credential_source_read_calls=0,
                settings_load_calls=0,
                oauth_load_calls=0,
                oauth_refresh_calls=0,
                oauth_operation_calls=0,
                oauth_token_view_reads=0,
                credential_close_verified=False,
                oauth_close_calls=0,
                oauth_close_verified=False,
                settings_off_locked_verified=False,
                private_resources_closed=False,
            )

        binding_ready = (
            binding_snapshot is not None
            and binding_snapshot.status is DormantBindingStatus.VERIFIED
            and binding_snapshot.binding_class == "sealed-in-memory-concrete"
        )
        concrete_ready = (
            concrete_snapshot is not None
            and concrete_snapshot.status is ConcreteBindingStatus.VERIFIED
            and concrete_snapshot.http_resource_factory_calls == 4
            and concrete_snapshot.close_calls == 4
        )
        verified = (
            m82.status is M82Status.READY
            and m82.settings_off_locked_verified
            and m82.private_resources_closed
            and binding_ready
            and concrete_ready
            and binding_oauth_close_calls == 1
            and https_verified
            and same_token_shared
        )
        cancelled = m82.status is M82Status.CANCELLED
        status = (
            M83Status.VERIFIED
            if verified
            else M83Status.CANCELLED if cancelled else M83Status.NO_GO
        )
        return M83HttpsOwnerSnapshot(
            phase="M83",
            status=status,
            reason=(
                "m83_m82_four_https_factories_verified_in_memory"
                if verified
                else (
                    "m83_owner_cancelled"
                    if cancelled
                    else "m83_owner_failed_safe"
                )
            ),
            owner_run_calls=1,
            credential_source_read_calls=m82.credential_source_read_calls,
            settings_load_calls=m82.settings_load_calls,
            oauth_load_calls=m82.oauth_load_calls,
            oauth_refresh_calls=0,
            oauth_token_view_reads=m82.oauth_token_view_reads,
            oauth_close_calls=m82.oauth_close_calls,
            oauth_close_verified=m82.oauth_close_verified,
            binding_oauth_loader_calls=(
                binding_snapshot.oauth_loader_calls if binding_snapshot else 0
            ),
            binding_oauth_close_calls=binding_oauth_close_calls,
            http_resource_factory_calls=(
                concrete_snapshot.http_resource_factory_calls
                if concrete_snapshot
                else 0
            ),
            concrete_builder_calls=(
                sum(
                    (
                        concrete_snapshot.nia_builder_calls,
                        concrete_snapshot.bitrix_builder_calls,
                        concrete_snapshot.deleter_builder_calls,
                        concrete_snapshot.history_builder_calls,
                    )
                )
                if concrete_snapshot
                else 0
            ),
            dependency_close_calls=(
                binding_snapshot.dependency_close_calls if binding_snapshot else 0
            ),
            http_close_calls=(
                concrete_snapshot.close_calls if concrete_snapshot else 0
            ),
            https_origins_verified=https_verified,
            same_private_token_shared=same_token_shared,
            construction_lazy_until_m82_operation=True,
            all_private_resources_closed=(
                m82.private_resources_closed
                and (
                    (
                        binding_snapshot is None
                        and concrete_snapshot is None
                    )
                    or (
                        binding_snapshot is not None
                        and concrete_snapshot is not None
                    )
                )
            ),
        )


__all__ = [
    "M83HttpsOwnerSnapshot",
    "M83InjectedHttpsOwner",
    "M83Status",
    "MockTransportFactory",
]
