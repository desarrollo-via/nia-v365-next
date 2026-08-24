"""Puente fail-closed para el montaje interno OAuth R1."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class OptionalR1OAuthRefreshInternalResult:
    mounted: bool
    reason: str


def _load_host_factories() -> tuple[Callable[[], Any], Callable[..., Any]]:
    bindings_module = importlib.import_module(
        "bitrix_connector.r1_oauth_refresh_host_bindings"
    )
    mount_module = importlib.import_module(
        "bitrix_connector.r1_oauth_refresh_internal_mount"
    )
    return (
        bindings_module.build_r1_oauth_refresh_host_bindings,
        mount_module.mount_r1_oauth_refresh_internal_router,
    )


def mount_optional_r1_oauth_refresh_internal(
    app: Any,
    *,
    factory_loader: Callable[[], tuple[Callable[[], Any], Callable[..., Any]]] | None = None,
    logger: logging.Logger | None = None,
) -> OptionalR1OAuthRefreshInternalResult:
    """Monta sólo una composición R1 completa; falla cerrado en otro caso."""

    try:
        build_bindings, mount_router = (factory_loader or _load_host_factories)()
        binding_result = build_bindings()
        if binding_result.bindings is None:
            return OptionalR1OAuthRefreshInternalResult(False, binding_result.reason)
        mount_result = mount_router(app, bindings=binding_result.bindings)
        return OptionalR1OAuthRefreshInternalResult(mount_result.mounted, mount_result.reason)
    except Exception as exc:
        if logger is not None:
            logger.warning(
                "r1_oauth_refresh_internal_mount_unavailable error_type=%s",
                type(exc).__name__,
            )
        return OptionalR1OAuthRefreshInternalResult(False, "composition_failed")


__all__ = [
    "OptionalR1OAuthRefreshInternalResult",
    "mount_optional_r1_oauth_refresh_internal",
]
