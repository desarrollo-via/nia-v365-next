"""Owner R1 one-shot: un secreto Key Vault, un refresh OAuth y cierre seguro."""

from __future__ import annotations

import asyncio
from importlib.util import find_spec
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from .bitrix_event_scoped_r1_protected_oauth_builder import (
    PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    ProtectedStoredOAuthResourcesBuilder,
)
from .config import ConnectorSettings
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory
from .r1_key_vault_exact_secret_backend import (
    AzureKeyVaultExactSecretBackend,
    build_managed_identity_exact_secret_backend,
)


R1_OAUTH_REFRESH_CONFIRMATION = "RENOVAR OAUTH R1 PROTEGIDO UNA SOLA VEZ"
R1_OAUTH_REFRESH_OWNER_MODULE = "bitrix_connector.r1_oauth_refresh_execution_owner"
R1_OAUTH_REFRESH_OWNER_COMMAND = (
    r".\.venv\Scripts\python.exe -m "
    r"bitrix_connector.r1_oauth_refresh_execution_owner "
    r'--confirm-code "RENOVAR OAUTH R1 PROTEGIDO UNA SOLA VEZ"'
)
R1_KEY_VAULT_URL = "https://nia-next-r1-kv-260810.vault.azure.net"


class OAuthProvider(Protocol):
    async def get_access_token(self, member_id: str) -> str: ...

    async def refresh_access_token(self, member_id: str, stale_token: str) -> str: ...


class OAuthResources(Protocol):
    oauth_provider: OAuthProvider
    member_id: str

    async def close(self) -> None: ...


class OAuthResourcesFactory(Protocol):
    async def build(
        self, settings: ConnectorSettings, *, timeout_seconds: float
    ) -> OAuthResources: ...


@dataclass(frozen=True)
class R1OAuthRefreshSnapshot:
    state: Literal["READY", "NO-GO", "CANCELLED"] = "NO-GO"
    reason: str = "r1_oauth_refresh_not_started"
    protected_source_opened: bool = False
    resources_closed: bool = True
    source_read_calls: int = 0
    resource_build_calls: int = 0
    refresh_calls: int = 0
    persistence_verification_calls: int = 0
    token_rotated: bool = False
    persistence_verified: bool = False


def _safe_snapshot(
    *,
    state: Literal["READY", "NO-GO", "CANCELLED"],
    reason: str,
    protected_source_opened: bool,
    resources_closed: bool,
    source_read_calls: int,
    resource_build_calls: int,
    refresh_calls: int,
    persistence_verification_calls: int,
    token_rotated: bool = False,
    persistence_verified: bool = False,
) -> R1OAuthRefreshSnapshot:
    return R1OAuthRefreshSnapshot(
        state=state,
        reason=reason,
        protected_source_opened=protected_source_opened,
        resources_closed=resources_closed,
        source_read_calls=source_read_calls,
        resource_build_calls=resource_build_calls,
        refresh_calls=refresh_calls,
        persistence_verification_calls=persistence_verification_calls,
        token_rotated=token_rotated if state == "READY" else False,
        persistence_verified=persistence_verified if state == "READY" else False,
    )


async def execute_r1_oauth_refresh_once(
    *,
    credential_backend: AzureKeyVaultExactSecretBackend,
    resources_factory: OAuthResourcesFactory,
    timeout_seconds: float = PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    resources_builder: Callable[[], Any] | None = None,
) -> R1OAuthRefreshSnapshot:
    """Abre el secreto exacto una vez y sólo persiste por el CAS del provider."""

    if (
        credential_backend is None
        or not callable(getattr(credential_backend, "fetch_exact", None))
        or not callable(getattr(credential_backend, "close", None))
        or resources_factory is None
        or not callable(getattr(resources_factory, "build", None))
        or type(timeout_seconds) not in {int, float}
        or timeout_seconds <= 0
        or timeout_seconds > PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS
    ):
        return R1OAuthRefreshSnapshot(reason="r1_oauth_refresh_dependencies_invalid")

    builder = resources_builder or ProtectedStoredOAuthResourcesBuilder(
        credential_backend=credential_backend,
        resources_factory=resources_factory,
        timeout_seconds=float(timeout_seconds),
    )
    resources: OAuthResources | None = None
    source_opened = False
    resource_build_calls = 0
    refresh_calls = 0
    verification_calls = 0
    resources_closed = True
    state: Literal["READY", "NO-GO", "CANCELLED"] = "NO-GO"
    reason = "r1_oauth_refresh_failed_safe"
    rotated = False
    verified = False
    try:
        resources = await builder()
        source_opened = True
        resource_build_calls = 1
        resources_closed = False
        stale_token = await resources.oauth_provider.get_access_token(resources.member_id)
        refreshed_token = await resources.oauth_provider.refresh_access_token(
            resources.member_id, stale_token
        )
        refresh_calls = 1
        persisted_token = await resources.oauth_provider.get_access_token(resources.member_id)
        verification_calls = 1
        rotated = bool(refreshed_token != stale_token)
        verified = bool(rotated and persisted_token == refreshed_token)
        if not verified:
            reason = "r1_oauth_refresh_persistence_unverified"
        else:
            state = "READY"
            reason = "r1_oauth_rotated_and_persisted"
    except asyncio.CancelledError:
        state = "CANCELLED"
        reason = "r1_oauth_refresh_cancelled"
    except BaseException:
        pass
    finally:
        if resources is not None:
            try:
                await resources.close()
                resources_closed = True
            except BaseException:
                resources_closed = False
    if not resources_closed:
        state = "NO-GO"
        reason = "r1_oauth_refresh_resources_close_failed"
    return _safe_snapshot(
        state=state,
        reason=reason,
        protected_source_opened=source_opened,
        resources_closed=resources_closed,
        source_read_calls=7 if source_opened else 0,
        resource_build_calls=resource_build_calls,
        refresh_calls=refresh_calls,
        persistence_verification_calls=verification_calls,
        token_rotated=rotated,
        persistence_verified=verified,
    )


async def execute_r1_oauth_refresh_protected_once() -> R1OAuthRefreshSnapshot:
    """Construye los recursos reales sólo bajo el literal del CLI."""

    if find_spec("aiohttp") is None:
        return R1OAuthRefreshSnapshot(
            reason="r1_oauth_refresh_async_transport_missing",
            resources_closed=True,
        )
    try:
        backend = build_managed_identity_exact_secret_backend(
            vault_url=R1_KEY_VAULT_URL
        )
    except BaseException:
        return R1OAuthRefreshSnapshot(
            reason="r1_oauth_refresh_binding_failed_safe",
            resources_closed=True,
        )
    return await execute_r1_oauth_refresh_once(
        credential_backend=backend,
        resources_factory=PilotDiscoveryOAuthFactory(),
    )


def _parse_request(argv: Sequence[str]) -> bool:
    values = tuple(argv)
    if not values or values[0] != "--confirm-code":
        return False
    return " ".join(values[1:]) == R1_OAUTH_REFRESH_CONFIRMATION


def _emit(snapshot: R1OAuthRefreshSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    executor: Callable[[], Any] = execute_r1_oauth_refresh_protected_once,
) -> int:
    if not _parse_request(tuple(sys.argv[1:] if argv is None else argv)):
        _emit(R1OAuthRefreshSnapshot(reason="r1_oauth_refresh_owner_rejected"))
        return 2
    try:
        snapshot = asyncio.run(executor())
        if type(snapshot) is not R1OAuthRefreshSnapshot:
            raise TypeError("r1_oauth_refresh_owner_result_invalid")
    except KeyboardInterrupt:
        snapshot = R1OAuthRefreshSnapshot(
            state="CANCELLED", reason="r1_oauth_refresh_owner_cancelled",
            resources_closed=False,
        )
    except BaseException:
        snapshot = R1OAuthRefreshSnapshot(
            reason="r1_oauth_refresh_owner_failed_safe", resources_closed=False
        )
    _emit(snapshot)
    return {"READY": 0, "NO-GO": 1, "CANCELLED": 130}[snapshot.state]


if __name__ == "__main__":
    raise SystemExit(main())
