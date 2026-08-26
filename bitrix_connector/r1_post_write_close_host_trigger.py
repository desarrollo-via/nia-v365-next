"""Protected one-shot host trigger for post-write R1 closure.

The route is inert while mounted.  Anonymous or invalid identities are
rejected before JWKS-dependent execution, and the process-local gate consumes
at most one authenticated invocation attempt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .r1_oauth_refresh_internal_router import (
    R1OAuthRefreshInternalRouterBindings,
)
from .r1_oauth_refresh_workload_identity_jwt import (
    verify_r1_workload_identity_jwt_once,
)
from .r1_post_write_close_recovery import PostWriteCloseResult


R1_POST_WRITE_CLOSE_TRIGGER_PATH = (
    "/bitrix-connector/r1/post-write-close/trigger"
)
PostWriteCloseExecutor = Callable[[], Awaitable[PostWriteCloseResult]]


def create_r1_post_write_close_host_trigger_router(
    *,
    auth_bindings: R1OAuthRefreshInternalRouterBindings,
    executor: PostWriteCloseExecutor,
) -> APIRouter:
    """Builds the protected route without constructing or running recovery."""

    if (
        type(auth_bindings) is not R1OAuthRefreshInternalRouterBindings
        or not callable(executor)
    ):
        raise TypeError("r1_post_write_close_trigger_bindings_invalid")
    router = APIRouter()
    lock = asyncio.Lock()
    used = False

    @router.post(R1_POST_WRITE_CLOSE_TRIGGER_PATH)
    async def close_once(request: Request) -> dict[str, object]:
        nonlocal used
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="r1_internal_identity_rejected",
            )
        jwks_by_kid: Mapping[str, Mapping[str, object]] = (
            auth_bindings.jwks_by_kid
        )
        jwks_resolver = getattr(auth_bindings, "jwks_resolver", None)
        if jwks_resolver is not None:
            try:
                jwks_by_kid = jwks_resolver()
            except BaseException:
                jwks_by_kid = {}
        identity = verify_r1_workload_identity_jwt_once(
            authorization.removeprefix("Bearer "),
            policy=auth_bindings.policy,
            jwks_by_kid=jwks_by_kid,
            now=auth_bindings.now_provider(),
        )
        if identity is None:
            raise HTTPException(
                status_code=401,
                detail="r1_internal_identity_rejected",
            )
        async with lock:
            if used:
                raise HTTPException(
                    status_code=409,
                    detail="r1_post_write_close_trigger_consumed",
                )
            used = True
        try:
            result = await executor()
        except BaseException:
            raise HTTPException(
                status_code=503,
                detail="r1_post_write_close_unavailable",
            ) from None
        if type(result) is not PostWriteCloseResult:
            raise HTTPException(
                status_code=503,
                detail="r1_post_write_close_result_invalid",
            )
        payload = asdict(result)
        if result.failure_surface == "restart_pending":
            return JSONResponse(status_code=202, content=payload)
        return payload

    return router


__all__ = [
    "PostWriteCloseExecutor",
    "R1_POST_WRITE_CLOSE_TRIGGER_PATH",
    "create_r1_post_write_close_host_trigger_router",
]
