"""M86-BL: fábrica real-ready dormida y fábrica fixture separada."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthBackend,
)
from .bitrix_history_r0_m86_combined_preflight_owner import AsyncClientFactory
from .bitrix_history_r0_m86_dormant_dotenv_preflight_binding import (
    M86BJ_DOTENV_PATH,
    M86BJFixturePreflightOwner,
)
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource


@dataclass(frozen=True)
class M86BLDormantFactoryPreview:
    phase: Literal["M86-BL"] = "M86-BL"
    state: Literal["DORMANT-REAL-FACTORY-DISABLED"] = (
        "DORMANT-REAL-FACTORY-DISABLED"
    )
    project_root_dotenv_bound: Literal[True] = True
    m86bi_backend_bound: Literal[True] = True
    stored_oauth_bound: Literal[True] = True
    m86c_owner_bound: Literal[True] = True
    real_factory_callable: Literal[True] = True
    real_execution_enabled: Literal[False] = False
    factory_calls: int = 0
    source_constructions: Literal[0] = 0
    source_open_calls: Literal[0] = 0
    oauth_factory_calls: Literal[0] = 0
    http_factory_calls: Literal[0] = 0
    authorization_received: Literal[False] = False
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86BLDormantRealOwnerFactory:
    """Conserva el blueprint real, pero toda invocación queda bloqueada."""

    __slots__ = ("_dotenv_path", "_factory_calls")

    def __init__(self) -> None:
        self._dotenv_path = M86BJ_DOTENV_PATH
        self._factory_calls = 0

    def preview(self) -> M86BLDormantFactoryPreview:
        return M86BLDormantFactoryPreview(factory_calls=self._factory_calls)

    def __call__(self):
        self._factory_calls += 1
        raise RuntimeError("m86bl_real_execution_disabled")

    def __repr__(self) -> str:
        return "M86BLDormantRealOwnerFactory(<redacted>)"


SourceFactory = Callable[[], AllowlistedDotenvSource]
OAuthBackendFactory = Callable[[], InjectedStoredOAuthBackend]


class M86BLFixtureOwnerFactory:
    """Construye exactamente un owner fixture desde tres fábricas inyectadas."""

    __slots__ = (
        "_http_factory",
        "_oauth_factory",
        "_source_factory",
        "_used",
        "calls",
    )

    def __init__(
        self,
        *,
        source_factory: SourceFactory,
        oauth_backend_factory: OAuthBackendFactory,
        http_client_factory: AsyncClientFactory,
    ) -> None:
        if not all(
            callable(value)
            for value in (
                source_factory,
                oauth_backend_factory,
                http_client_factory,
            )
        ):
            raise TypeError("m86bl_fixture_factory_dependency_invalid")
        self._source_factory: SourceFactory | None = source_factory
        self._oauth_factory: OAuthBackendFactory | None = oauth_backend_factory
        self._http_factory: AsyncClientFactory | None = http_client_factory
        self._used = False
        self.calls = 0

    def __call__(self) -> M86BJFixturePreflightOwner:
        if (
            self._used
            or self._source_factory is None
            or self._oauth_factory is None
            or self._http_factory is None
        ):
            self._used = True
            raise RuntimeError("m86bl_fixture_factory_reused")
        self._used = True
        self.calls = 1
        source_factory, self._source_factory = self._source_factory, None
        oauth_factory, self._oauth_factory = self._oauth_factory, None
        http_factory, self._http_factory = self._http_factory, None
        source = source_factory()
        oauth = oauth_factory()
        if type(source) is not AllowlistedDotenvSource or oauth is None:
            raise TypeError("m86bl_fixture_factory_result_invalid")
        return M86BJFixturePreflightOwner(
            source=source,
            oauth_backend=oauth,
            http_client_factory=http_factory,
        )


@dataclass(frozen=True)
class M86BLDormantFactoryContract:
    phase: Literal["M86-BL"] = "M86-BL"
    state: Literal["DORMANT-REAL-FACTORY-DISABLED"] = (
        "DORMANT-REAL-FACTORY-DISABLED"
    )
    exact_project_root_path: Literal[True] = True
    real_factory_is_fail_closed: Literal[True] = True
    fixture_factory_separate: Literal[True] = True
    real_source_construction_budget: Literal[0] = 0
    real_source_open_budget: Literal[0] = 0
    oauth_budget: Literal[0] = 0
    network_budget: Literal[0] = 0
    cli_available: Literal[False] = False
    external_calls: Literal[0] = 0


def build_dormant_m86bl_real_owner_factory() -> M86BLDormantRealOwnerFactory:
    return M86BLDormantRealOwnerFactory()


__all__ = [
    "M86BLDormantFactoryContract",
    "M86BLDormantFactoryPreview",
    "M86BLDormantRealOwnerFactory",
    "M86BLFixtureOwnerFactory",
    "build_dormant_m86bl_real_owner_factory",
]
