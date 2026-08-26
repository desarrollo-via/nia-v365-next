"""Bindings mínimos del host para la ruta interna OAuth R1.

Sólo consulta cuatro App Settings nombrados. No enumera configuración, no abre
secretos y deja el owner OAuth real fuera del montaje publicado.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.request import urlopen
from urllib.parse import urlparse

from .r1_oauth_refresh_execution_owner import execute_r1_oauth_refresh_protected_once
from .r1_oauth_refresh_internal_router import R1OAuthRefreshInternalRouterBindings
from .r1_oauth_refresh_workload_identity_auth import (
    build_r1_internal_workload_identity_policy,
)
from .r1_post_write_close_host_binding import (
    build_r1_post_write_persistent_host_executor,
)


R1_OAUTH_REFRESH_ISSUER_SETTING = "R1_OAUTH_REFRESH_ISSUER"
R1_OAUTH_REFRESH_AUDIENCE_SETTING = "R1_OAUTH_REFRESH_AUDIENCE"
R1_OAUTH_REFRESH_AUTHORIZED_CLIENT_ID_SETTING = "R1_OAUTH_REFRESH_AUTHORIZED_CLIENT_ID"
R1_OAUTH_REFRESH_JWKS_URI_SETTING = "R1_OAUTH_REFRESH_JWKS_URI"
R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST = (
    R1_OAUTH_REFRESH_ISSUER_SETTING,
    R1_OAUTH_REFRESH_AUDIENCE_SETTING,
    R1_OAUTH_REFRESH_AUTHORIZED_CLIENT_ID_SETTING,
    R1_OAUTH_REFRESH_JWKS_URI_SETTING,
)
MANAGED_IDENTITY_MAX_TOKEN_AGE_SECONDS = 86_400


def _managed_identity_v1_issuer(v2_issuer: str) -> str | None:
    try:
        parsed = urlparse(v2_issuer)
    except ValueError:
        return None
    parts = tuple(part for part in parsed.path.split("/") if part)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "login.microsoftonline.com"
        or len(parts) != 2
        or parts[1] != "v2.0"
    ):
        return None
    tenant = parts[0]
    if not tenant or any(character not in "0123456789abcdefABCDEF-" for character in tenant):
        return None
    return f"https://sts.windows.net/{tenant}/"


@dataclass(frozen=True)
class R1OAuthRefreshHostBindingResult:
    bindings: R1OAuthRefreshInternalRouterBindings | None
    reason: str
    post_write_close_executor: object | None = None


def _read_required_setting(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _load_jwks_once(uri: str) -> Mapping[str, Mapping[str, object]]:
    """Obtiene sólo JWKS público, bajo bearer; limita tamaño y forma."""

    with urlopen(uri, timeout=3) as response:  # nosec B310: URI allowlisted below
        payload = response.read(262_145)
    if len(payload) > 262_144:
        return {}
    parsed = json.loads(payload)
    keys = parsed.get("keys") if type(parsed) is dict else None
    if type(keys) is not list:
        return {}
    return {
        key["kid"]: key
        for key in keys
        if type(key) is dict and type(key.get("kid")) is str and key["kid"].strip()
    }


def build_r1_oauth_refresh_host_bindings() -> R1OAuthRefreshHostBindingResult:
    """Construye el allowlist; falla cerrado sin listar ni revelar valores."""

    values = {name: _read_required_setting(name) for name in R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST}
    if any(value is None for value in values.values()):
        return R1OAuthRefreshHostBindingResult(None, "configuration_missing")
    jwks_uri = values[R1_OAUTH_REFRESH_JWKS_URI_SETTING]
    if not (jwks_uri.startswith("https://login.microsoftonline.com/") and jwks_uri.endswith("/discovery/v2.0/keys")):
        return R1OAuthRefreshHostBindingResult(None, "jwks_uri_rejected")
    alternate_issuer = _managed_identity_v1_issuer(
        values[R1_OAUTH_REFRESH_ISSUER_SETTING]
    )
    if alternate_issuer is None:
        return R1OAuthRefreshHostBindingResult(None, "issuer_rejected")
    policy = build_r1_internal_workload_identity_policy(
        issuer=values[R1_OAUTH_REFRESH_ISSUER_SETTING],
        audience=values[R1_OAUTH_REFRESH_AUDIENCE_SETTING],
        authorized_client_id=values[R1_OAUTH_REFRESH_AUTHORIZED_CLIENT_ID_SETTING],
        maximum_token_age_seconds=MANAGED_IDENTITY_MAX_TOKEN_AGE_SECONDS,
        alternate_issuer=alternate_issuer,
        allow_appid_client_claim=True,
    )
    return R1OAuthRefreshHostBindingResult(
        R1OAuthRefreshInternalRouterBindings(
            policy=policy,
            jwks_by_kid={},
            jwks_resolver=lambda: _load_jwks_once(jwks_uri),
            executor=execute_r1_oauth_refresh_protected_once,
        ),
        "ready",
        build_r1_post_write_persistent_host_executor(),
    )


__all__ = [
    "R1_OAUTH_REFRESH_HOST_SETTING_ALLOWLIST",
    "R1OAuthRefreshHostBindingResult",
    "build_r1_oauth_refresh_host_bindings",
]
