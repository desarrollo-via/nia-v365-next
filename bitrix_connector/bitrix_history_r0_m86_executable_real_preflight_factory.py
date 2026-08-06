"""M86-BN: fábrica final ejecutable tras M86-BK y readiness sin invocarla."""

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
    M86BKAuthorizationContract,
    M86BKAuthorizationGate,
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
class M86BNFactoryPreview:
    phase: Literal["M86-BN"] = "M86-BN"
    state: Literal["WAITING-EXACT-AUTHORIZATION"] = "WAITING-EXACT-AUTHORIZATION"
    gate_permit_required: Literal[True] = True
    direct_call_allowed: Literal[False] = False
    owner_hermetic_execution: Literal[True] = True
    permit_consumed: bool = False
    factory_calls: int = 0
    source_constructions: int = 0
    oauth_constructions: int = 0
    owner_constructions: int = 0
    real_source_open_calls: Literal[0] = 0
    real_oauth_load_calls: Literal[0] = 0
    real_http_calls: Literal[0] = 0
    authorization_received: Literal[False] = False
    external_calls: Literal[0] = 0


class M86BNGatePermittedExecutableOwnerFactory:
    """Sólo el permit M86-BK puede construir el owner ejecutable one-shot."""

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
            raise TypeError("m86bn_factory_dependency_invalid")
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
        raise RuntimeError("m86bn_gate_permit_required")

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
            raise RuntimeError("m86bn_factory_reuse_or_permit_invalid")
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
            raise TypeError("m86bn_source_invalid")
        oauth = oauth_builder()
        self.oauth_constructions = 1
        if type(oauth) is not M86StoredOAuthBackend:
            raise TypeError("m86bn_oauth_invalid")
        owner = owner_builder(
            credential_backend=M86BIInjectedDotenvCredentialBackend(source=source),
            oauth_backend=oauth,
            http_client_factory=http_factory,
            hermetic_execution=True,
        )
        self.owner_constructions = 1
        if type(owner) is not M86CombinedPreflightOwner:
            raise TypeError("m86bn_owner_invalid")
        return owner

    def preview(self) -> M86BNFactoryPreview:
        return M86BNFactoryPreview(
            permit_consumed=self._permit_consumed,
            factory_calls=self.factory_calls,
            source_constructions=self.source_constructions,
            oauth_constructions=self.oauth_constructions,
            owner_constructions=self.owner_constructions,
        )


@dataclass(frozen=True)
class M86BNReadinessSnapshot:
    phase: Literal["M86-BN"] = "M86-BN"
    state: Literal["READY-TO-SHOW-PREFLIGHT-AUTHORIZATION", "NO-GO"] = "NO-GO"
    exact_gate_bound: bool = False
    executable_factory_dormant: bool = False
    literal_prepared: bool = False
    literal_shown: Literal[False] = False
    authorization_received: Literal[False] = False
    real_source_open_calls: Literal[0] = 0
    real_oauth_load_calls: Literal[0] = 0
    real_http_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86bn_readiness(
    *,
    factory: M86BNGatePermittedExecutableOwnerFactory,
    authorization: M86BKAuthorizationContract,
) -> M86BNReadinessSnapshot:
    if (
        type(factory) is not M86BNGatePermittedExecutableOwnerFactory
        or type(authorization) is not M86BKAuthorizationContract
    ):
        return M86BNReadinessSnapshot()
    preview = factory.preview()
    ready = (
        preview.state == "WAITING-EXACT-AUTHORIZATION"
        and preview.gate_permit_required
        and not preview.direct_call_allowed
        and preview.owner_hermetic_execution
        and not preview.permit_consumed
        and preview.factory_calls == 0
        and preview.source_constructions == 0
        and preview.oauth_constructions == 0
        and preview.owner_constructions == 0
        and authorization.state == "PREPARED-NOT-SHOWN"
        and not authorization.shown_to_person
        and not authorization.authorization_received
        and not authorization.linked_to_real_execution
        and authorization.current_real_open_budget == 0
        and authorization.current_oauth_budget == 0
        and authorization.current_bitrix_read_budget == 0
    )
    return M86BNReadinessSnapshot(
        state="READY-TO-SHOW-PREFLIGHT-AUTHORIZATION" if ready else "NO-GO",
        exact_gate_bound=True,
        executable_factory_dormant=True,
        literal_prepared=True,
    )


def build_m86bn_real_authorization_gate() -> M86BKAuthorizationGate:
    factory = M86BNGatePermittedExecutableOwnerFactory(
        source_builder=lambda: AllowlistedDotenvSource(M86BJ_DOTENV_PATH),
        oauth_builder=build_real_m86_stored_oauth_backend,
        http_client_factory=build_real_m86_https_async_client,
    )
    return M86BKAuthorizationGate(
        owner_factory=factory,
        execution_profile="real",
    )


__all__ = [
    "M86BNFactoryPreview",
    "M86BNGatePermittedExecutableOwnerFactory",
    "M86BNReadinessSnapshot",
    "audit_m86bn_readiness",
    "build_m86bn_real_authorization_gate",
]
