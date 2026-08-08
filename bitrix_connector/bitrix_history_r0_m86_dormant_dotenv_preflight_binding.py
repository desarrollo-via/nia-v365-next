"""M86-BJ: binding dotenv real dormido y ensayo separado sólo inyectado."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthBackend,
)
from .bitrix_history_r0_m86_combined_preflight_owner import (
    AsyncClientFactory,
    M86CombinedPreflightOwner,
    M86CombinedPreflightSnapshot,
)
from .bitrix_history_r0_m86_dotenv_m81_backend import (
    M86BIInjectedDotenvCredentialBackend,
)
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource


M86BJ_PROJECT_ROOT = Path(__file__).resolve().parent.parent
M86BJ_DOTENV_PATH = M86BJ_PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class M86BJDormantPreview:
    phase: Literal["M86-BJ"] = "M86-BJ"
    state: Literal["DORMANT-BOUND-NOT-EXECUTABLE"] = (
        "DORMANT-BOUND-NOT-EXECUTABLE"
    )
    project_root_dotenv_bound: Literal[True] = True
    m86bi_backend_bound: Literal[True] = True
    m86c_owner_bound: Literal[True] = True
    path_checked: Literal[False] = False
    path_opened: Literal[False] = False
    source_factory_calls: Literal[0] = 0
    oauth_factory_calls: Literal[0] = 0
    http_factory_calls: Literal[0] = 0
    execution_surface_available: Literal[False] = False
    authorization_received: Literal[False] = False
    real_open_budget: Literal[0] = 0
    real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86BJDormantDotenvPreflightBinding:
    """Referencia la topología real sin exponer build, run o CLI."""

    __slots__ = ("_dotenv_path",)

    def __init__(self) -> None:
        self._dotenv_path = M86BJ_DOTENV_PATH

    def preview(self) -> M86BJDormantPreview:
        return M86BJDormantPreview()

    def __repr__(self) -> str:
        return "M86BJDormantDotenvPreflightBinding(<redacted>)"


class M86BJFixturePreflightOwner:
    """Ensayo one-shot: sólo dependencias explícitamente inyectadas."""

    __slots__ = ("_http_factory", "_oauth_backend", "_source", "_used")

    def __init__(
        self,
        *,
        source: AllowlistedDotenvSource,
        oauth_backend: InjectedStoredOAuthBackend,
        http_client_factory: AsyncClientFactory,
    ) -> None:
        if (
            type(source) is not AllowlistedDotenvSource
            or oauth_backend is None
            or not callable(http_client_factory)
        ):
            raise TypeError("m86bj_fixture_dependency_invalid")
        self._source: AllowlistedDotenvSource | None = source
        self._oauth_backend: InjectedStoredOAuthBackend | None = oauth_backend
        self._http_factory: AsyncClientFactory | None = http_client_factory
        self._used = False

    async def run_once(self) -> M86CombinedPreflightSnapshot:
        if (
            self._used
            or self._source is None
            or self._oauth_backend is None
            or self._http_factory is None
        ):
            self._used = True
            raise RuntimeError("m86bj_fixture_owner_reused")
        self._used = True
        source, self._source = self._source, None
        oauth, self._oauth_backend = self._oauth_backend, None
        http_factory, self._http_factory = self._http_factory, None
        return await M86CombinedPreflightOwner(
            credential_backend=M86BIInjectedDotenvCredentialBackend(source=source),
            oauth_backend=oauth,
            http_client_factory=http_factory,
            hermetic_execution=True,
        ).run_once()

    def __repr__(self) -> str:
        return "M86BJFixturePreflightOwner(<redacted>)"


@dataclass(frozen=True)
class M86BJDormantBindingContract:
    phase: Literal["M86-BJ"] = "M86-BJ"
    state: Literal["DORMANT-BOUND-NOT-EXECUTABLE"] = (
        "DORMANT-BOUND-NOT-EXECUTABLE"
    )
    exact_project_root_path: Literal[True] = True
    real_binding_has_execute: Literal[False] = False
    real_binding_has_cli: Literal[False] = False
    fixture_owner_separate: Literal[True] = True
    real_open_budget: Literal[0] = 0
    oauth_budget: Literal[0] = 0
    network_budget: Literal[0] = 0
    external_calls: Literal[0] = 0


def build_dormant_m86bj_binding() -> M86BJDormantDotenvPreflightBinding:
    return M86BJDormantDotenvPreflightBinding()


__all__ = [
    "M86BJDormantBindingContract",
    "M86BJDormantDotenvPreflightBinding",
    "M86BJDormantPreview",
    "M86BJFixturePreflightOwner",
    "build_dormant_m86bj_binding",
]
