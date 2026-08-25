"""Trigger interno one-shot del host para el invocador OAuth R1.

El trigger no se ejecuta al montar el host. Sólo un bearer de identidad de
carga validado puede alcanzar el invocador; una petición anónima se rechaza
antes de resolver JWKS, pedir un token de identidad o tocar el owner OAuth.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from azure.identity.aio import ManagedIdentityCredential
from fastapi import APIRouter, HTTPException, Request

from .r1_oauth_refresh_host_invoker import (
    R1OAuthRefreshHostInvocationSnapshot,
    invoke_r1_oauth_refresh_from_host_once,
)
from .r1_oauth_refresh_internal_endpoint import R1_OAUTH_REFRESH_INTERNAL_PATH
from .r1_oauth_refresh_internal_router import R1OAuthRefreshInternalRouterBindings
from .r1_oauth_refresh_workload_identity_jwt import verify_r1_workload_identity_jwt_once


R1_OAUTH_REFRESH_HOST_TRIGGER_PATH = "/bitrix-connector/r1/oauth-refresh/trigger"
HostInvoker = Callable[[], Awaitable[R1OAuthRefreshHostInvocationSnapshot]]


@dataclass(frozen=True)
class R1OAuthRefreshHostTriggerBindings:
    router_bindings: R1OAuthRefreshInternalRouterBindings
    invoker: HostInvoker


def _managed_identity_scope(audience: str) -> str:
    return audience if audience.endswith("/.default") else f"{audience.rstrip('/')}/.default"


def _build_host_invoker(
    app: object, *, audience: str
) -> HostInvoker:
    scope = _managed_identity_scope(audience)

    async def token_provider() -> str:
        credential = ManagedIdentityCredential()
        try:
            token = await credential.get_token(scope)
            return token.token
        finally:
            await credential.close()

    async def endpoint_caller(path: str, token: str) -> int:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://r1-internal"
        ) as client:
            response = await client.post(
                path, headers={"Authorization": f"Bearer {token}"}
            )
        return response.status_code

    async def invoke_once() -> R1OAuthRefreshHostInvocationSnapshot:
        return await invoke_r1_oauth_refresh_from_host_once(
            token_provider=token_provider, endpoint_caller=endpoint_caller
        )

    return invoke_once


def create_r1_oauth_refresh_host_trigger_router(
    app: object, *, bindings: R1OAuthRefreshInternalRouterBindings
) -> APIRouter:
    """Monta el trigger protegido sin pedir token ni invocar OAuth."""

    if type(bindings) is not R1OAuthRefreshInternalRouterBindings:
        raise TypeError("r1_host_trigger_bindings_required")
    trigger_bindings = R1OAuthRefreshHostTriggerBindings(
        router_bindings=bindings,
        invoker=_build_host_invoker(app, audience=bindings.policy.audience),
    )
    router = APIRouter()

    @router.post(R1_OAUTH_REFRESH_HOST_TRIGGER_PATH)
    async def trigger_once(request: Request) -> dict[str, object]:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="r1_internal_identity_rejected")
        router_bindings = trigger_bindings.router_bindings
        jwks_by_kid: Mapping[str, Mapping[str, object]] = router_bindings.jwks_by_kid
        if router_bindings.jwks_resolver is not None:
            try:
                jwks_by_kid = router_bindings.jwks_resolver()
            except BaseException:
                jwks_by_kid = {}
        identity = verify_r1_workload_identity_jwt_once(
            authorization.removeprefix("Bearer "),
            policy=router_bindings.policy,
            jwks_by_kid=jwks_by_kid,
            now=router_bindings.now_provider(),
        )
        if identity is None:
            raise HTTPException(status_code=401, detail="r1_internal_identity_rejected")
        snapshot = await trigger_bindings.invoker()
        return {
            "state": snapshot.state,
            "reason": snapshot.reason,
            "token_requests": snapshot.token_requests,
            "endpoint_requests": snapshot.endpoint_requests,
        }

    return router


__all__ = [
    "R1_OAUTH_REFRESH_HOST_TRIGGER_PATH",
    "R1OAuthRefreshHostTriggerBindings",
    "create_r1_oauth_refresh_host_trigger_router",
]
