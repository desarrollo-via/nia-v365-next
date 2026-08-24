"""Ruta R1 inerte: se construye por inyección y no se monta en producción."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from .r1_oauth_refresh_execution_owner import R1OAuthRefreshSnapshot, R1_OAUTH_REFRESH_CONFIRMATION
from .r1_oauth_refresh_internal_endpoint import (
    EndpointExecutor,
    R1_OAUTH_REFRESH_INTERNAL_PATH,
    authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once,
    build_r1_oauth_refresh_internal_endpoint_plan,
)
from .r1_oauth_refresh_workload_identity_auth import R1InternalWorkloadIdentityPolicy
from .r1_oauth_refresh_workload_identity_jwt import verify_r1_workload_identity_jwt_once


@dataclass(frozen=True)
class R1OAuthRefreshInternalRouterBindings:
    policy: R1InternalWorkloadIdentityPolicy
    jwks_by_kid: Mapping[str, Mapping[str, object]]
    executor: EndpointExecutor
    now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    jwks_resolver: Callable[[], Mapping[str, Mapping[str, object]]] | None = None


def create_r1_oauth_refresh_internal_router(
    bindings: R1OAuthRefreshInternalRouterBindings,
) -> APIRouter:
    """Crea una ruta no montada; no lee configuración ni construye el owner."""

    if type(bindings) is not R1OAuthRefreshInternalRouterBindings:
        raise TypeError("r1_internal_router_bindings_required")
    router = APIRouter()

    @router.post(R1_OAUTH_REFRESH_INTERNAL_PATH)
    async def refresh_once(request: Request) -> dict[str, object]:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="r1_internal_identity_rejected")
        now = bindings.now_provider()
        jwks_by_kid = bindings.jwks_by_kid
        if bindings.jwks_resolver is not None:
            try:
                jwks_by_kid = bindings.jwks_resolver()
            except BaseException:
                jwks_by_kid = {}
        identity = verify_r1_workload_identity_jwt_once(
            authorization.removeprefix("Bearer "),
            policy=bindings.policy,
            jwks_by_kid=jwks_by_kid,
            now=now,
        )
        snapshot = await authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once(
            build_r1_oauth_refresh_internal_endpoint_plan(),
            policy=bindings.policy,
            identity=identity,
            now=now,
            confirmation=R1_OAUTH_REFRESH_CONFIRMATION,
            executor=bindings.executor,
        )
        if snapshot.reason == "r1_internal_identity_rejected":
            raise HTTPException(status_code=401, detail=snapshot.reason)
        return asdict(snapshot)

    return router


__all__ = [
    "R1OAuthRefreshInternalRouterBindings",
    "create_r1_oauth_refresh_internal_router",
]
