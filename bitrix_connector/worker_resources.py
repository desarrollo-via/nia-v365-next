"""Recursos exclusivos del proceso worker, construidos de forma fail-closed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from .bitrix_client import BitrixClient
from .config import ConnectorMode, ConnectorSettings, load_settings
from .mode_policy import ExternalCallPolicyProvider, current_external_call_policy
from .nia_client import NiaClient
from .pilot_scope import PilotScopePolicy, PilotScopePolicyProvider
from .oauth import (
    BitrixOAuthCredentialProvider,
    BitrixOAuthTransport,
    MongoBitrixOAuthStore,
)
from .storage import MongoConnectorEventStore
from .worker_composition import ConnectorWorkerComposition, compose_workers


class WorkerResourcesConfigurationError(ValueError):
    """La ejecución fue habilitada sin configuración completa y segura."""


def current_pilot_scope_policy() -> PilotScopePolicy:
    """Reconstruye el alcance en cada despacho; configuración inválida cierra."""

    settings = load_settings()
    configuration_invalid = not settings.pilot_configuration_valid
    return PilotScopePolicy(
        enabled=settings.pilot_enabled or configuration_invalid,
        rules=settings.pilot_rules,
        emergency_stop=settings.pilot_emergency_stop or configuration_invalid,
    )


@dataclass(frozen=True)
class WorkerResourceOptions:
    worker_id: str
    lease_seconds: int = 60
    default_retry_after_seconds: int = 30
    http_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("worker_id no puede estar vacío")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds debe ser positivo")
        if self.default_retry_after_seconds <= 0:
            raise ValueError("default_retry_after_seconds debe ser positivo")
        if self.http_timeout_seconds <= 0:
            raise ValueError("http_timeout_seconds debe ser positivo")


@dataclass
class ConnectorWorkerResources:
    """Posee todos los recursos creados exclusivamente para un worker."""

    mongo_client: Any
    nia_client: Any
    oauth_transport: Any
    bitrix_client: Any
    composition: ConnectorWorkerComposition
    _closed: bool = field(default=False, init=False, repr=False)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        first_error: Optional[BaseException] = None
        for close in (
            self.bitrix_client.close,
            self.oauth_transport.close,
            self.nia_client.close,
        ):
            try:
                await close()
            except BaseException as exc:  # pragma: no cover - defensa de cierre
                first_error = first_error or exc
        try:
            self.mongo_client.close()
        except BaseException as exc:  # pragma: no cover - defensa de cierre
            first_error = first_error or exc
        if first_error is not None:
            raise first_error


def _required(value: Optional[str], error_code: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise WorkerResourcesConfigurationError(error_code)
    return cleaned


def _nia_root_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    parsed = httpx.URL(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise WorkerResourcesConfigurationError("worker_nia_base_url_invalid")
    if parsed.userinfo or parsed.query or parsed.fragment:
        raise WorkerResourcesConfigurationError("worker_nia_base_url_invalid")
    if parsed.path not in {"", "/"}:
        raise WorkerResourcesConfigurationError("worker_nia_base_url_invalid")
    return cleaned


def _portal_url(domain: str) -> str:
    cleaned = domain.strip().rstrip("/")
    if cleaned.lower().startswith("https://"):
        portal_url = cleaned
    elif "://" not in cleaned:
        portal_url = f"https://{cleaned}"
    else:
        raise WorkerResourcesConfigurationError("worker_bitrix_domain_invalid")

    parsed = httpx.URL(portal_url)
    if parsed.scheme != "https" or not parsed.host:
        raise WorkerResourcesConfigurationError("worker_bitrix_domain_invalid")
    if parsed.userinfo or parsed.query or parsed.fragment:
        raise WorkerResourcesConfigurationError("worker_bitrix_domain_invalid")
    if parsed.path not in {"", "/"}:
        raise WorkerResourcesConfigurationError("worker_bitrix_domain_invalid")
    return portal_url


class ConnectorWorkerResourcesFactory:
    """Construye Mongo y HTTP solo después de superar las tres barreras."""

    def __init__(
        self,
        *,
        mongo_client_factory: Any = AsyncIOMotorClient,
        nia_client_factory: Callable[..., Any] = NiaClient,
        oauth_transport_factory: Callable[..., Any] = BitrixOAuthTransport,
        oauth_provider_factory: Callable[..., Any] = BitrixOAuthCredentialProvider,
        bitrix_client_factory: Callable[..., Any] = BitrixClient,
        composition_factory: Callable[..., ConnectorWorkerComposition] = compose_workers,
        policy_provider: ExternalCallPolicyProvider = current_external_call_policy,
        pilot_policy_provider: PilotScopePolicyProvider = current_pilot_scope_policy,
    ) -> None:
        self._mongo_client_factory = mongo_client_factory
        self._nia_client_factory = nia_client_factory
        self._oauth_transport_factory = oauth_transport_factory
        self._oauth_provider_factory = oauth_provider_factory
        self._bitrix_client_factory = bitrix_client_factory
        self._composition_factory = composition_factory
        self._policy_provider = policy_provider
        self._pilot_policy_provider = pilot_policy_provider

    async def build(
        self,
        settings: ConnectorSettings,
        options: WorkerResourceOptions,
    ) -> Optional[ConnectorWorkerResources]:
        if (
            settings.activation_locked
            or settings.effective_mode is ConnectorMode.OFF
            or not settings.external_calls_enabled
        ):
            return None

        mongo_uri = _required(settings.mongo_uri, "worker_mongo_uri_not_configured")
        mongo_db = _required(settings.mongo_db, "worker_mongo_db_not_configured")
        events_collection = _required(
            settings.events_collection,
            "worker_events_collection_not_configured",
        )
        installations_collection = _required(
            settings.installations_collection,
            "worker_installations_collection_not_configured",
        )
        nia_base_url = _nia_root_url(
            _required(
                settings.nia_base_url,
                "worker_nia_base_url_not_configured",
            )
        )
        portal_url = _portal_url(
            _required(
                settings.bitrix_domain,
                "worker_bitrix_domain_not_configured",
            )
        )
        member_id = _required(
            settings.bitrix_member_id,
            "worker_bitrix_member_id_not_configured",
        )
        client_id = _required(
            settings.bitrix_client_id,
            "worker_bitrix_client_id_not_configured",
        )
        client_secret = _required(
            settings.bitrix_client_secret,
            "worker_bitrix_client_secret_not_configured",
        )

        mongo_client = self._mongo_client_factory(
            mongo_uri,
            tz_aware=True,
        )
        nia_client = None
        oauth_transport = None
        bitrix_client = None
        try:
            database = mongo_client[mongo_db]
            event_store = MongoConnectorEventStore.from_database(
                database,
                events_collection,
            )
            oauth_store = MongoBitrixOAuthStore(
                database[installations_collection]
            )
            await event_store.ensure_indexes()
            await oauth_store.ensure_indexes()

            nia_client = self._nia_client_factory(
                base_url=nia_base_url,
                timeout_seconds=options.http_timeout_seconds,
            )
            oauth_transport = self._oauth_transport_factory(
                client_id=client_id,
                client_secret=client_secret,
                timeout_seconds=options.http_timeout_seconds,
            )
            oauth_provider = self._oauth_provider_factory(
                oauth_store,
                oauth_transport,
            )
            bitrix_client = self._bitrix_client_factory(
                portal_url=portal_url,
                token_provider=oauth_provider,
                member_id=member_id,
                timeout_seconds=options.http_timeout_seconds,
            )
            composition = self._composition_factory(
                event_store,
                nia_client,
                bitrix_client,
                worker_id=options.worker_id,
                lease_seconds=options.lease_seconds,
                default_retry_after_seconds=options.default_retry_after_seconds,
                policy_provider=self._policy_provider,
                pilot_policy_provider=self._pilot_policy_provider,
            )
        except BaseException:
            for resource in (bitrix_client, oauth_transport, nia_client):
                if resource is None:
                    continue
                try:
                    await resource.close()
                except BaseException:
                    pass
            try:
                mongo_client.close()
            except BaseException:
                pass
            raise

        return ConnectorWorkerResources(
            mongo_client=mongo_client,
            nia_client=nia_client,
            oauth_transport=oauth_transport,
            bitrix_client=bitrix_client,
            composition=composition,
        )
