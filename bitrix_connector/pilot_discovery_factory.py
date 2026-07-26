"""Recursos OAuth mínimos para descubrir chats sin activar el conector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from .config import ConnectorSettings
from .oauth import (
    BitrixOAuthCredentialProvider,
    BitrixOAuthTransport,
    MongoBitrixOAuthStore,
)


class PilotDiscoveryConfigurationError(ValueError):
    """La consulta no dispone de una configuración OAuth completa."""


def _required(value: Optional[str], error_code: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise PilotDiscoveryConfigurationError(error_code)
    return cleaned


def _portal_url(domain: str) -> str:
    cleaned = domain.strip().rstrip("/")
    candidate = (
        cleaned
        if cleaned.lower().startswith("https://")
        else f"https://{cleaned}"
    )
    parsed = httpx.URL(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.host
        or parsed.userinfo
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise PilotDiscoveryConfigurationError(
            "pilot_discovery_bitrix_domain_invalid"
        )
    return candidate


@dataclass
class PilotDiscoveryOAuthResources:
    mongo_client: Any
    oauth_transport: Any
    oauth_provider: Any
    portal_url: str
    member_id: str

    async def close(self) -> None:
        first_error: Optional[BaseException] = None
        try:
            await self.oauth_transport.close()
        except BaseException as exc:  # pragma: no cover - cierre defensivo
            first_error = exc
        try:
            self.mongo_client.close()
        except BaseException as exc:  # pragma: no cover - cierre defensivo
            first_error = first_error or exc
        if first_error is not None:
            raise first_error


class PilotDiscoveryOAuthFactory:
    """Compone solo Mongo OAuth y renovación; no crea worker ni clientes de envío."""

    def __init__(
        self,
        *,
        mongo_client_factory: Any = AsyncIOMotorClient,
        oauth_transport_factory: Callable[..., Any] = BitrixOAuthTransport,
        oauth_provider_factory: Callable[..., Any] = BitrixOAuthCredentialProvider,
    ) -> None:
        self._mongo_client_factory = mongo_client_factory
        self._oauth_transport_factory = oauth_transport_factory
        self._oauth_provider_factory = oauth_provider_factory

    async def build(
        self,
        settings: ConnectorSettings,
        *,
        timeout_seconds: float,
    ) -> PilotDiscoveryOAuthResources:
        if timeout_seconds <= 0:
            raise PilotDiscoveryConfigurationError(
                "pilot_discovery_timeout_invalid"
            )
        mongo_uri = _required(
            settings.mongo_uri,
            "pilot_discovery_mongo_uri_not_configured",
        )
        mongo_db = _required(
            settings.mongo_db,
            "pilot_discovery_mongo_db_not_configured",
        )
        collection_name = _required(
            settings.installations_collection,
            "pilot_discovery_installations_collection_not_configured",
        )
        member_id = _required(
            settings.bitrix_member_id,
            "pilot_discovery_member_id_not_configured",
        )
        client_id = _required(
            settings.bitrix_client_id,
            "pilot_discovery_client_id_not_configured",
        )
        client_secret = _required(
            settings.bitrix_client_secret,
            "pilot_discovery_client_secret_not_configured",
        )
        portal_url = _portal_url(
            _required(
                settings.bitrix_domain,
                "pilot_discovery_bitrix_domain_not_configured",
            )
        )

        mongo_client = self._mongo_client_factory(mongo_uri, tz_aware=True)
        oauth_transport = None
        try:
            store = MongoBitrixOAuthStore(
                mongo_client[mongo_db][collection_name]
            )
            oauth_transport = self._oauth_transport_factory(
                client_id=client_id,
                client_secret=client_secret,
                timeout_seconds=timeout_seconds,
            )
            oauth_provider = self._oauth_provider_factory(
                store,
                oauth_transport,
            )
            return PilotDiscoveryOAuthResources(
                mongo_client=mongo_client,
                oauth_transport=oauth_transport,
                oauth_provider=oauth_provider,
                portal_url=portal_url,
                member_id=member_id,
            )
        except BaseException:
            if oauth_transport is not None:
                try:
                    await oauth_transport.close()
                except BaseException:
                    pass
            mongo_client.close()
            raise
