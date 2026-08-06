"""M86-BM: fábrica one-shot con permiso M86-BK y owner aún no ejecutable."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_combined_preflight_owner import (
    AsyncClientFactory,
    M86CombinedPreflightOwner,
)
from .bitrix_history_r0_m86_dormant_dotenv_preflight_binding import (
    M86BJ_DOTENV_PATH,
)
from .bitrix_history_r0_m86_dotenv_m81_backend import (
    M86BIInjectedDotenvCredentialBackend,
)
from .bitrix_history_r0_m86_dotenv_preflight_authorization_gate import (
    _M86BKFactoryPermit,
)
from .bitrix_history_r0_m86_real_https_factory import (
    build_real_m86_https_async_client,
)
from .bitrix_history_r0_m86_stored_oauth_backend import (
    M86StoredOAuthBackend,
    build_real_m86_stored_oauth_backend,
)
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource


SourceBuilder = Callable[[], AllowlistedDotenvSource]
OAuthBuilder = Callable[[], M86StoredOAuthBackend]
OwnerBuilder = Callable[..., M86CombinedPreflightOwner]


@dataclass(frozen=True)
class M86BMFactoryPreview:
    phase: Literal["M86-BM"] = "M86-BM"
    state: Literal["GATE-PERMITTED-NOT-EXECUTABLE"] = (
        "GATE-PERMITTED-NOT-EXECUTABLE"
    )
    direct_call_allowed: Literal[False] = False
    gate_permit_required: Literal[True] = True
    permit_consumed: bool = False
    factory_calls: int = 0
    source_constructions: int = 0
    oauth_constructions: int = 0
    owner_constructions: int = 0
    owner_hermetic_execution: Literal[False] = False
    source_open_calls: Literal[0] = 0
    oauth_load_calls: Literal[0] = 0
    http_calls: Literal[0] = 0
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0


class M86BMGatePermittedRealOwnerFactory:
    """Compone una vez tras el permit; el owner resultante sólo hace preview."""

    __slots__ = (
        "_http_factory",
        "_oauth_builder",
        "_owner_builder",
        "_permit_consumed",
        "_source_builder",
        "_used",
        "factory_calls",
        "oauth_constructions",
        "owner_constructions",
        "source_constructions",
    )

    def __init__(
        self,
        *,
        source_builder: SourceBuilder,
        oauth_builder: OAuthBuilder,
        http_client_factory: AsyncClientFactory,
        owner_builder: OwnerBuilder = M86CombinedPreflightOwner,
    ) -> None:
        if not all(
            callable(value)
            for value in (
                source_builder,
                oauth_builder,
                http_client_factory,
                owner_builder,
            )
        ):
            raise TypeError("m86bm_factory_dependency_invalid")
        self._source_builder: SourceBuilder | None = source_builder
        self._oauth_builder: OAuthBuilder | None = oauth_builder
        self._http_factory: AsyncClientFactory | None = http_client_factory
        self._owner_builder: OwnerBuilder | None = owner_builder
        self._used = False
        self._permit_consumed = False
        self.factory_calls = 0
        self.source_constructions = 0
        self.oauth_constructions = 0
        self.owner_constructions = 0

    def __call__(self):
        raise RuntimeError("m86bm_gate_permit_required")

    def build_after_gate_once(
        self, permit: _M86BKFactoryPermit
    ) -> M86CombinedPreflightOwner:
        if (
            self._used
            or type(permit) is not _M86BKFactoryPermit
            or self._source_builder is None
            or self._oauth_builder is None
            or self._http_factory is None
            or self._owner_builder is None
        ):
            self._used = True
            raise RuntimeError("m86bm_factory_reuse_or_permit_invalid")
        self._used = True
        self._permit_consumed = True
        self.factory_calls = 1
        source_builder, self._source_builder = self._source_builder, None
        oauth_builder, self._oauth_builder = self._oauth_builder, None
        http_factory, self._http_factory = self._http_factory, None
        owner_builder, self._owner_builder = self._owner_builder, None

        source = source_builder()
        self.source_constructions = 1
        if type(source) is not AllowlistedDotenvSource:
            raise TypeError("m86bm_source_invalid")
        oauth = oauth_builder()
        self.oauth_constructions = 1
        if type(oauth) is not M86StoredOAuthBackend:
            raise TypeError("m86bm_oauth_invalid")
        owner = owner_builder(
            credential_backend=M86BIInjectedDotenvCredentialBackend(source=source),
            oauth_backend=oauth,
            http_client_factory=http_factory,
            hermetic_execution=False,
        )
        self.owner_constructions = 1
        if type(owner) is not M86CombinedPreflightOwner:
            raise TypeError("m86bm_owner_invalid")
        return owner

    def preview(self) -> M86BMFactoryPreview:
        return M86BMFactoryPreview(
            permit_consumed=self._permit_consumed,
            factory_calls=self.factory_calls,
            source_constructions=self.source_constructions,
            oauth_constructions=self.oauth_constructions,
            owner_constructions=self.owner_constructions,
        )

    def __repr__(self) -> str:
        return "M86BMGatePermittedRealOwnerFactory(<redacted>)"


@dataclass(frozen=True)
class M86BMFactoryContract:
    phase: Literal["M86-BM"] = "M86-BM"
    state: Literal["GATE-PERMITTED-NOT-EXECUTABLE"] = (
        "GATE-PERMITTED-NOT-EXECUTABLE"
    )
    exact_gate_permit_required: Literal[True] = True
    direct_call_allowed: Literal[False] = False
    one_shot: Literal[True] = True
    owner_hermetic_execution: Literal[False] = False
    real_source_open_budget: Literal[0] = 0
    real_oauth_load_budget: Literal[0] = 0
    real_http_budget: Literal[0] = 0
    cli_available: Literal[False] = False
    external_calls: Literal[0] = 0


def build_m86bm_gate_permitted_real_owner_factory(
) -> M86BMGatePermittedRealOwnerFactory:
    return M86BMGatePermittedRealOwnerFactory(
        source_builder=lambda: AllowlistedDotenvSource(M86BJ_DOTENV_PATH),
        oauth_builder=build_real_m86_stored_oauth_backend,
        http_client_factory=build_real_m86_https_async_client,
    )


__all__ = [
    "M86BMFactoryContract",
    "M86BMFactoryPreview",
    "M86BMGatePermittedRealOwnerFactory",
    "build_m86bm_gate_permitted_real_owner_factory",
]
