"""Host ASGI mínimo para la ventana de instalación OAuth de Bitrix24."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import ConnectorSettings, load_settings
from .installation_factory import OAuthInstallationFactory
from .installation_router import OAuthInstaller, create_installation_router


INSTALLATION_PREFIX = "/bitrix-connector"
INSTALLATION_CALLBACK_PATH = f"{INSTALLATION_PREFIX}/installation"


def create_installation_entrypoint(
    *,
    installer: Optional[OAuthInstaller] = None,
    settings_loader: Callable[[], ConnectorSettings] = load_settings,
    resources_factory: Optional[OAuthInstallationFactory] = None,
) -> FastAPI:
    """Compone exclusivamente el callback y un health sin secretos."""

    app = FastAPI(
        title="NIA Bitrix OAuth Installation",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "127.0.0.1",
            "localhost",
            "*.trycloudflare.com",
        ],
        www_redirect=False,
    )
    app.include_router(
        create_installation_router(
            installer,
            settings_loader=settings_loader,
            resources_factory=resources_factory,
        ),
        prefix=INSTALLATION_PREFIX,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        settings = settings_loader()
        return {
            "status": "ok",
            "service": "bitrix_oauth_installation",
            "effective_mode": settings.effective_mode.value,
            "activation_locked": settings.activation_locked,
            "external_calls_enabled": settings.external_calls_enabled,
            "installation_enabled": settings.installation_enabled,
            "pilot_enabled": settings.pilot_enabled,
            "pilot_emergency_stop": settings.pilot_emergency_stop,
        }

    app.state.bitrix_oauth_installation_entrypoint = True
    app.state.bitrix_oauth_callback_path = INSTALLATION_CALLBACK_PATH
    return app


app = create_installation_entrypoint()


__all__ = [
    "INSTALLATION_CALLBACK_PATH",
    "INSTALLATION_PREFIX",
    "app",
    "create_installation_entrypoint",
]
