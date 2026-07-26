"""Puente mínimo para montar bitrix_connector sin acoplarlo a NIA Next."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Optional


MODULE_ENABLED_ENV = "NIA_BITRIX_MODULE_ENABLED"
_MOUNTED_ATTRIBUTE = "_nia_bitrix_connector_router_mounted"


class OptionalModuleStatus(str, Enum):
    DISABLED = "disabled"
    MOUNTED = "mounted"
    ALREADY_MOUNTED = "already_mounted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OptionalModuleMountResult:
    status: OptionalModuleStatus
    enabled: bool
    reason: str


def _switch_value(environ: Mapping[str, str]) -> tuple[bool, str]:
    raw = (environ.get(MODULE_ENABLED_ENV) or "").strip().lower()
    if raw == "true":
        return True, "module_enabled"
    if raw in {"", "false"}:
        return False, "module_disabled"
    return False, "module_switch_invalid"


def is_bitrix_connector_enabled(
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    enabled, _ = _switch_value(os.environ if environ is None else environ)
    return enabled


def _load_router() -> Any:
    module = importlib.import_module("bitrix_connector.router")
    return module.router


def mount_optional_bitrix_connector(
    app: Any,
    *,
    environ: Optional[Mapping[str, str]] = None,
    router_loader: Optional[Callable[[], Any]] = None,
    logger: Optional[logging.Logger] = None,
) -> OptionalModuleMountResult:
    """Monta el router solo con el switch literal ``true``.

    El paquete se importa de forma diferida. Si está ausente o su import falla,
    NIA continúa sin el conector y el log conserva únicamente el tipo de error.
    """

    enabled, reason = _switch_value(os.environ if environ is None else environ)
    if not enabled:
        return OptionalModuleMountResult(
            status=OptionalModuleStatus.DISABLED,
            enabled=False,
            reason=reason,
        )

    if getattr(app, _MOUNTED_ATTRIBUTE, False):
        return OptionalModuleMountResult(
            status=OptionalModuleStatus.ALREADY_MOUNTED,
            enabled=True,
            reason="router_already_mounted",
        )

    try:
        router = (router_loader or _load_router)()
    except Exception as exc:  # el módulo opcional no bloquea el núcleo
        if logger is not None:
            logger.warning(
                "bitrix_connector_mount_unavailable error_type=%s",
                type(exc).__name__,
            )
        return OptionalModuleMountResult(
            status=OptionalModuleStatus.UNAVAILABLE,
            enabled=True,
            reason="router_import_failed",
        )

    app.include_router(router)
    setattr(app, _MOUNTED_ATTRIBUTE, True)
    return OptionalModuleMountResult(
        status=OptionalModuleStatus.MOUNTED,
        enabled=True,
        reason="router_mounted",
    )


__all__ = [
    "MODULE_ENABLED_ENV",
    "OptionalModuleMountResult",
    "OptionalModuleStatus",
    "is_bitrix_connector_enabled",
    "mount_optional_bitrix_connector",
]
