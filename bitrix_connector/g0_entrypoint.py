"""Aplicación ASGI mínima para el ingreso inerte G0."""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import CONNECTOR_VERSION
from .config import ConnectorSettings, load_settings
from .g0_guard import (
    G0IngressGuard,
    G0IngressGuardMiddleware,
    G0IngressLimits,
    G0StopController,
)
from .models import WebhookReceipt
from .webhook_handler import handle_bitrix_webhook


G0_HEALTH_PATH = "/healthz"
G0_WEBHOOK_PATH = "/bitrix-connector/webhook"


def _stable_https_host(public_origin: str) -> str:
    parsed = urlsplit(public_origin.strip().rstrip("/"))
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("g0_public_origin_invalid") from exc

    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port not in (None, 443)
        or host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".trycloudflare.com")
        or "*" in host
    ):
        raise ValueError("g0_public_origin_invalid")
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("g0_public_origin_invalid")
    return host


def create_g0_entrypoint(
    *,
    public_origin: str,
    settings_loader: Callable[[], ConnectorSettings] = load_settings,
    limits: G0IngressLimits = G0IngressLimits(),
    stop_controller: G0StopController | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    """Expone solo salud y webhook sin runtime, startup o cliente externo."""

    trusted_host = _stable_https_host(public_origin)
    stop = stop_controller or G0StopController()
    guard = G0IngressGuard(
        limits=limits,
        stop_controller=stop,
        **({"clock": clock} if clock is not None else {}),
    )
    app = FastAPI(
        title="NIA Bitrix G0 Ingress",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    @app.get(G0_HEALTH_PATH)
    async def healthz() -> dict[str, object]:
        settings = settings_loader()
        return {
            "status": "ok",
            "service": "bitrix_g0_ingress",
            "version": CONNECTOR_VERSION,
            "effective_mode": settings.effective_mode.value,
            "activation_locked": settings.activation_locked,
            "external_calls_enabled": settings.external_calls_enabled,
            "pilot_enabled": settings.pilot_enabled,
            "pilot_emergency_stop": settings.pilot_emergency_stop,
            "accepting_webhooks": not stop.stopped,
        }

    @app.post(G0_WEBHOOK_PATH, response_model=WebhookReceipt)
    async def webhook(request: Request):
        return await handle_bitrix_webhook(
            request,
            settings_loader=settings_loader,
            runtime=None,
        )

    app.add_middleware(
        G0IngressGuardMiddleware,
        guard=guard,
        webhook_path=G0_WEBHOOK_PATH,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[trusted_host],
        www_redirect=False,
    )

    app.state.bitrix_g0_entrypoint = True
    app.state.bitrix_g0_trusted_host = trusted_host
    app.state.bitrix_g0_runtime_attached = False
    app.state.bitrix_g0_limits = limits
    app.state.bitrix_g0_guard = guard
    app.state.bitrix_g0_stop_controller = stop
    return app


__all__ = [
    "G0_HEALTH_PATH",
    "G0_WEBHOOK_PATH",
    "create_g0_entrypoint",
]
