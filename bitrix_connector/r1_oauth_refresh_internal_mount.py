"""Montaje explícito e inerte de la ruta OAuth R1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .r1_oauth_refresh_internal_router import (
    R1OAuthRefreshInternalRouterBindings,
    create_r1_oauth_refresh_internal_router,
)
from .r1_oauth_refresh_host_trigger import (
    create_r1_oauth_refresh_host_trigger_router,
)
from .r1_post_write_close_host_trigger import (
    create_r1_post_write_close_host_trigger_router,
)


_MOUNTED_ATTRIBUTE = "_nia_r1_oauth_refresh_internal_router_mounted"


@dataclass(frozen=True)
class R1OAuthRefreshInternalMountResult:
    mounted: bool
    reason: str


def mount_r1_oauth_refresh_internal_router(
    app: Any,
    *,
    bindings: R1OAuthRefreshInternalRouterBindings,
    post_write_close_executor=None,
) -> R1OAuthRefreshInternalMountResult:
    """Monta sólo bindings inyectados; no lee configuración ni secretos."""

    if type(bindings) is not R1OAuthRefreshInternalRouterBindings:
        raise TypeError("r1_internal_router_bindings_required")
    if getattr(app, _MOUNTED_ATTRIBUTE, False):
        return R1OAuthRefreshInternalMountResult(False, "already_mounted")
    app.include_router(create_r1_oauth_refresh_internal_router(bindings))
    app.include_router(
        create_r1_oauth_refresh_host_trigger_router(app, bindings=bindings)
    )
    if post_write_close_executor is not None:
        app.include_router(create_r1_post_write_close_host_trigger_router(
            auth_bindings=bindings,
            executor=post_write_close_executor,
        ))
    setattr(app, _MOUNTED_ATTRIBUTE, True)
    return R1OAuthRefreshInternalMountResult(True, "mounted")


__all__ = [
    "R1OAuthRefreshInternalMountResult",
    "mount_r1_oauth_refresh_internal_router",
]
