"""Rutas GET protegidas para la trazabilidad integral del conector."""

from __future__ import annotations

from typing import Callable, Optional, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from .audit import AuditEventDetailResponse, AuditEventListResponse
from .audit_service import AuditDocumentInvalid
from .audit_resources import (
    AuditReaderResources,
    AuditResourcesConfigurationError,
    ConnectorAuditReaderFactory,
)
from .config import ConnectorSettings, load_settings
from .models import ConnectorEventStatus
from .security import validate_review_access

NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class AuditReaderFactory(Protocol):
    def open(self, settings: ConnectorSettings) -> AuditReaderResources: ...


def create_audit_router(
    reader_factory: Optional[AuditReaderFactory] = None,
    *,
    settings_loader: Callable[[], ConnectorSettings] = load_settings,
) -> APIRouter:
    router = APIRouter(prefix="/audit/events", tags=["Bitrix Connector Audit"])
    factory = reader_factory or ConnectorAuditReaderFactory()

    def authorize(
        authorization: str = Header(default=""),
    ) -> ConnectorSettings:
        settings = settings_loader()
        decision = validate_review_access(authorization, settings)
        if decision.accepted:
            return settings
        if decision.reason == "review_token_not_configured":
            raise HTTPException(
                status_code=503,
                detail="review_token_not_configured",
                headers=NO_STORE_HEADERS,
            )
        raise HTTPException(
            status_code=401,
            detail="review_unauthorized",
            headers={**NO_STORE_HEADERS, "WWW-Authenticate": "Bearer"},
        )

    def no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

    def validate_event_key(event_key: str) -> None:
        if len(event_key) != 64 or any(
            character not in "0123456789abcdef" for character in event_key
        ):
            raise HTTPException(
                status_code=404,
                detail="audit_event_not_found",
                headers=NO_STORE_HEADERS,
            )

    def unavailable(exc: Exception) -> HTTPException:
        if isinstance(exc, AuditDocumentInvalid):
            detail = "audit_document_invalid"
        elif isinstance(exc, AuditResourcesConfigurationError):
            detail = exc.code
        else:
            detail = "audit_storage_unavailable"
        return HTTPException(
            status_code=503,
            detail=detail,
            headers=NO_STORE_HEADERS,
        )

    @router.get("", response_model=AuditEventListResponse)
    async def list_events(
        response: Response,
        status: Optional[ConnectorEventStatus] = None,
        limit: int = Query(default=50, ge=1, le=100),
        settings: ConnectorSettings = Depends(authorize),
    ) -> AuditEventListResponse:
        no_store(response)
        try:
            resources = factory.open(settings)
            async with resources as reader:
                return await reader.list_events(status=status, limit=limit)
        except Exception as exc:
            raise unavailable(exc) from exc

    @router.get("/{event_key}", response_model=AuditEventDetailResponse)
    async def get_event(
        event_key: str,
        response: Response,
        settings: ConnectorSettings = Depends(authorize),
    ) -> AuditEventDetailResponse:
        no_store(response)
        validate_event_key(event_key)
        try:
            resources = factory.open(settings)
            async with resources as reader:
                item = await reader.get_event(event_key)
        except Exception as exc:
            raise unavailable(exc) from exc
        if item is None:
            raise HTTPException(
                status_code=404,
                detail="audit_event_not_found",
                headers=NO_STORE_HEADERS,
            )
        return item

    return router
