"""Montaje host opcional y fail-closed para el ingreso inerte Wazzup R0."""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


WAZZUP_R0_INGRESS_SWITCH = "NIA_WAZZUP_R0_ADAPTER_ENABLED"
_MOUNTED_ATTRIBUTE = "_nia_wazzup_r0_ingress_mounted"


class OptionalWazzupR0IngressStatus(str, Enum):
    DISABLED = "disabled"
    MOUNTED = "mounted"
    ALREADY_MOUNTED = "already_mounted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OptionalWazzupR0IngressResult:
    status: OptionalWazzupR0IngressStatus
    enabled: bool
    reason: str


class ExactPathASGIDispatchMiddleware:
    """Delega una única ruta exacta sin leer ni transformar la solicitud."""

    def __init__(self, app: Any, *, ingress_app: Any, path: str) -> None:
        self._app = app
        self._ingress_app = ingress_app
        self._path = path

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == self._path:
            await self._ingress_app(scope, receive, send)
            return
        await self._app(scope, receive, send)


def _switch_value(environ: Mapping[str, str]) -> tuple[bool, bool]:
    raw = (environ.get(WAZZUP_R0_INGRESS_SWITCH) or "").strip().lower()
    if raw == "true":
        return True, True
    if raw in {"", "false"}:
        return False, True
    return False, False


def _load_ingress_factory() -> tuple[Callable[..., Any], str]:
    module = importlib.import_module("bitrix_connector.wazzup_r0_ingress")
    return module.build_optional_wazzup_r0_ingress, module.WAZZUP_R0_INGRESS_PATH


def _warn_type(
    logger: Optional[logging.Logger],
    event: str,
    exc: Exception,
) -> None:
    if logger is not None:
        logger.warning("%s error_type=%s", event, type(exc).__name__)


def mount_optional_wazzup_r0_ingress(
    app: Any,
    *,
    environ: Optional[Mapping[str, str]] = None,
    scope: Any = None,
    header_verifier: Optional[Callable[[Mapping[str, str]], bool]] = None,
    ingress_factory_loader: Optional[
        Callable[[], tuple[Callable[..., Any], str]]
    ] = None,
    logger: Optional[logging.Logger] = None,
) -> OptionalWazzupR0IngressResult:
    """Añade un dispatcher exacto solo con composición local completa.

    La aplicación principal llama esta función sin identidad ni autenticador
    reales. Por eso incluso un switch ``true`` permanece cerrado hasta que un
    corte posterior aporte esas dependencias de manera explícita y verificada.
    """

    selected_environ = os.environ if environ is None else environ
    requested, valid = _switch_value(selected_environ)
    if not valid:
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.UNAVAILABLE,
            enabled=False,
            reason="wazzup_r0_ingress_switch_invalid",
        )
    if not requested:
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.DISABLED,
            enabled=False,
            reason="wazzup_r0_ingress_disabled",
        )
    if getattr(app, _MOUNTED_ATTRIBUTE, False):
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.ALREADY_MOUNTED,
            enabled=True,
            reason="wazzup_r0_ingress_already_mounted",
        )
    if scope is None or header_verifier is None:
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.UNAVAILABLE,
            enabled=False,
            reason="wazzup_r0_ingress_dependencies_missing",
        )

    try:
        ingress_factory, ingress_path = (
            ingress_factory_loader or _load_ingress_factory
        )()
        mount = ingress_factory(
            selected_environ,
            scope=scope,
            header_verifier=header_verifier,
        )
    except Exception as exc:
        _warn_type(logger, "wazzup_r0_ingress_composition_unavailable", exc)
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.UNAVAILABLE,
            enabled=False,
            reason="wazzup_r0_ingress_composition_failed",
        )

    if not mount.enabled or mount.app is None:
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.UNAVAILABLE,
            enabled=False,
            reason="wazzup_r0_ingress_not_ready",
        )

    try:
        app.add_middleware(
            ExactPathASGIDispatchMiddleware,
            ingress_app=mount.app,
            path=ingress_path,
        )
    except Exception as exc:
        _warn_type(logger, "wazzup_r0_ingress_mount_unavailable", exc)
        return OptionalWazzupR0IngressResult(
            status=OptionalWazzupR0IngressStatus.UNAVAILABLE,
            enabled=False,
            reason="wazzup_r0_ingress_mount_failed",
        )

    setattr(app, _MOUNTED_ATTRIBUTE, True)
    return OptionalWazzupR0IngressResult(
        status=OptionalWazzupR0IngressStatus.MOUNTED,
        enabled=True,
        reason="wazzup_r0_ingress_mounted_local_only",
    )


__all__ = [
    "ExactPathASGIDispatchMiddleware",
    "OptionalWazzupR0IngressResult",
    "OptionalWazzupR0IngressStatus",
    "WAZZUP_R0_INGRESS_SWITCH",
    "mount_optional_wazzup_r0_ingress",
]
