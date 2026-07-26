"""Entrypoint ASGI administrativo independiente y no ejecutable por defecto."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Callable, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .review_admin import (
    ReviewAdminAuthenticator,
    ReviewAdminDecisionController,
    ReviewAdminReadController,
    ReviewAdminSafetyState,
    create_review_admin_app,
)
from .review_admin_session import InMemoryReviewAdminSessionStore


async def _close_owned_resources(resources: Sequence[object]) -> None:
    first_error: Optional[Exception] = None
    seen: set[int] = set()
    for resource in reversed(resources):
        identity = id(resource)
        if identity in seen:
            continue
        seen.add(identity)
        close = getattr(resource, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise RuntimeError("review_admin_owned_resource_close_failed") from first_error


def create_review_admin_entrypoint(
    *,
    admin_origin: str,
    authenticator: ReviewAdminAuthenticator,
    decision_controller: ReviewAdminDecisionController,
    safety_loader: Callable[[], ReviewAdminSafetyState],
    review_controller: Optional[ReviewAdminReadController] = None,
    session_store: Optional[InMemoryReviewAdminSessionStore] = None,
    owned_resources: Optional[Sequence[object]] = None,
) -> FastAPI:
    """Compone un host exclusivo sin importar ni modificar la aplicación NIA."""

    parsed = urlsplit(admin_origin.strip().rstrip("/"))
    trusted_host = parsed.hostname
    if parsed.scheme != "https" or not trusted_host:
        raise ValueError("review_admin_entrypoint_origin_invalid")

    resources = tuple(
        owned_resources
        if owned_resources is not None
        else tuple(
            resource
            for resource in (
                authenticator,
                review_controller,
                decision_controller,
            )
            if resource is not None
        )
    )

    async def close_owned() -> None:
        await _close_owned_resources(resources)

    app = create_review_admin_app(
        admin_origin=admin_origin,
        authenticator=authenticator,
        decision_controller=decision_controller,
        review_controller=review_controller,
        safety_loader=safety_loader,
        session_store=session_store,
        shutdown_callback=close_owned,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[trusted_host],
        www_redirect=False,
    )
    app.state.review_admin_entrypoint = True
    app.state.review_admin_trusted_host = trusted_host
    return app


__all__ = ["create_review_admin_entrypoint"]
