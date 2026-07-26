"""Recursos efímeros y fail-closed para la lectura administrativa."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from .audit_service import AuditStore, ConnectorAuditService
from .config import ConnectorSettings
from .storage import MongoConnectorEventStore


class AuditResourcesConfigurationError(ValueError):
    """Configuración incompleta; el código es seguro para una respuesta HTTP."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _required(value: Optional[str], code: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise AuditResourcesConfigurationError(code)
    return cleaned


def _mongo_store(database: Any, collection_name: str) -> AuditStore:
    return MongoConnectorEventStore.from_database(database, collection_name)


@dataclass
class AuditReaderResources:
    """Posee un cliente por petición y garantiza su cierre idempotente."""

    mongo_client: Any
    reader: ConnectorAuditService
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.mongo_client.close()

    async def __aenter__(self) -> ConnectorAuditService:
        return self.reader

    async def __aexit__(self, *_: object) -> None:
        self.close()


class ConnectorAuditReaderFactory:
    """Construye solo lectura; no crea índices, colecciones ni documentos."""

    def __init__(
        self,
        *,
        mongo_client_factory: Any = AsyncIOMotorClient,
        store_factory: Callable[[Any, str], AuditStore] = _mongo_store,
        reader_factory: Callable[[AuditStore], ConnectorAuditService] = (
            ConnectorAuditService
        ),
    ) -> None:
        self._mongo_client_factory = mongo_client_factory
        self._store_factory = store_factory
        self._reader_factory = reader_factory

    def open(self, settings: ConnectorSettings) -> AuditReaderResources:
        """Valida todo antes de construir Motor, incluso bajo modo ``off``."""

        _required(settings.review_token, "audit_review_token_not_configured")
        mongo_uri = _required(
            settings.mongo_uri,
            "audit_mongo_uri_not_configured",
        )
        mongo_db = _required(
            settings.mongo_db,
            "audit_mongo_db_not_configured",
        )
        collection_name = _required(
            settings.events_collection,
            "audit_events_collection_not_configured",
        )

        mongo_client = self._mongo_client_factory(
            mongo_uri,
            connect=False,
        )
        try:
            store = self._store_factory(
                mongo_client[mongo_db],
                collection_name,
            )
            reader = self._reader_factory(store)
            return AuditReaderResources(
                mongo_client=mongo_client,
                reader=reader,
            )
        except BaseException:
            mongo_client.close()
            raise
