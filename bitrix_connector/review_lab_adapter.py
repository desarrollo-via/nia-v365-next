"""Adaptadores de solo lectura para alimentar dinámicamente el Review Lab."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from .audit import (
    AuditAttemptCounts,
    AuditEventDetailResponse,
    AuditEventListItem,
    AuditEventListResponse,
    AuditShadowResult,
    AuditStoredDecision,
)
from .models import ConnectorEventStatus
from .review_lab import build_simulated_review_lab_view


AUDIT_EVENTS_PATH = "/bitrix-connector/audit/events"


class ReviewLabSource(str, Enum):
    FIXTURE = "fixture"
    API = "api"


class ReviewLabSnapshot(BaseModel):
    """Estado completo de pantalla; nunca contiene credenciales."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: ReviewLabSource
    read_only: Literal[True] = True
    actions_enabled: Literal[False] = False
    banner: str
    events: AuditEventListResponse
    selected: Optional[AuditEventDetailResponse] = None


class ReviewLabAuditAdapter(Protocol):
    @property
    def source(self) -> ReviewLabSource: ...

    async def list_events(
        self,
        *,
        status: Optional[ConnectorEventStatus] = None,
        limit: int = 50,
    ) -> AuditEventListResponse: ...

    async def get_event(
        self,
        event_key: str,
    ) -> Optional[AuditEventDetailResponse]: ...


class ReviewLabAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_fixture_audit_detail() -> AuditEventDetailResponse:
    view = build_simulated_review_lab_view()
    return AuditEventDetailResponse(
        event_key=view.event_key,
        status=ConnectorEventStatus.SHADOWED,
        received_at=view.received_at,
        updated_at=view.updated_at,
        identity_verified=True,
        security_reason="fixture_identity_verified",
        original_event_redacted=view.original_event_redacted,
        normalized_message=view.normalized_message,
        attachment_manifest=view.attachment_manifest,
        nia_payload=view.nia_payload,
        input_content_hash=view.input_content_hash,
        input_decision=AuditStoredDecision(
            decision="approved",
            source="fixture",
            effective_mode=view.safety.scenario_mode,
            content_hash=view.input_content_hash,
            actor="fixture-adapter",
            reason="local_shadow_scenario",
            decided_at=view.updated_at,
        ),
        nia_response=view.nia_response,
        bitrix_payload_preview=view.bitrix_payload_preview,
        output_content_hash=view.output_content_hash,
        output_decision=None,
        workflow_guard=view.workflow_guard,
        shadow_result=AuditShadowResult(
            reason="bitrix_suppressed_by_shadow",
            effective_mode=view.safety.scenario_mode,
            content_hash=view.output_content_hash,
            completed_at=view.updated_at,
        ),
        outbound_message_id=None,
        attempts=AuditAttemptCounts(processing=1, nia=1, bitrix=0),
        processing_stage=None,
        last_error=None,
    )


class FixtureReviewLabAdapter:
    """Imita exactamente los dos GET sin abrir sockets ni archivos."""

    def __init__(
        self,
        detail: Optional[AuditEventDetailResponse] = None,
    ) -> None:
        self._detail = detail or build_fixture_audit_detail()

    @property
    def source(self) -> ReviewLabSource:
        return ReviewLabSource.FIXTURE

    async def list_events(
        self,
        *,
        status: Optional[ConnectorEventStatus] = None,
        limit: int = 50,
    ) -> AuditEventListResponse:
        detail = self._detail
        items = ()
        if limit > 0 and (status is None or status is detail.status):
            items = (
                AuditEventListItem(
                    event_key=detail.event_key,
                    status=detail.status,
                    received_at=detail.received_at,
                    updated_at=detail.updated_at,
                    message_id=(
                        detail.normalized_message.message_id
                        if detail.normalized_message
                        else None
                    ),
                    dialog_id=(
                        detail.normalized_message.dialog_id
                        if detail.normalized_message
                        else None
                    ),
                    observed_mode=detail.workflow_guard.last_observed_mode,
                    has_nia_response=detail.nia_response is not None,
                    has_bitrix_preview=(
                        detail.bitrix_payload_preview is not None
                    ),
                    bitrix_written=detail.outbound_message_id is not None,
                ),
            )
        return AuditEventListResponse(items=items, returned=len(items))

    async def get_event(
        self,
        event_key: str,
    ) -> Optional[AuditEventDetailResponse]:
        if event_key != self._detail.event_key:
            return None
        return self._detail.model_copy(deep=True)


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class HttpReviewLabAdapter:
    """Cliente GET inyectable; no ofrece verbos ni métodos de escritura."""

    def __init__(
        self,
        *,
        base_url: str,
        review_token: str,
        timeout_seconds: float = 10.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        cleaned_url = base_url.strip().rstrip("/")
        parsed = httpx.URL(cleaned_url)
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            raise ValueError("review_lab_base_url_invalid")
        if parsed.userinfo or parsed.query or parsed.fragment:
            raise ValueError("review_lab_base_url_invalid")
        if parsed.path not in {"", "/"}:
            raise ValueError("review_lab_base_url_must_be_root")
        if timeout_seconds <= 0:
            raise ValueError("review_lab_timeout_invalid")
        if not review_token.strip():
            raise ValueError("review_lab_token_required")

        self._endpoint = f"{cleaned_url}{AUDIT_EVENTS_PATH}"
        self._review_token = SecretStr(review_token.strip())
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    @property
    def source(self) -> ReviewLabSource:
        return ReviewLabSource.API

    async def _get(
        self,
        url: str,
        model: type[ResponseModel],
        *,
        params: Optional[dict[str, object]] = None,
    ) -> ResponseModel:
        try:
            response = await self._http_client.get(
                url,
                params=params,
                headers={
                    "Authorization": (
                        "Bearer " + self._review_token.get_secret_value()
                    ),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
            )
        except httpx.TimeoutException as exc:
            raise ReviewLabAdapterError("review_lab_api_timeout") from exc
        except httpx.TransportError as exc:
            raise ReviewLabAdapterError("review_lab_api_unavailable") from exc

        if response.status_code == 401:
            raise ReviewLabAdapterError("review_lab_api_unauthorized")
        if response.status_code == 404:
            raise ReviewLabAdapterError("review_lab_event_not_found")
        if not 200 <= response.status_code <= 299:
            raise ReviewLabAdapterError("review_lab_api_unavailable")
        try:
            return model.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ReviewLabAdapterError("review_lab_api_invalid_response") from exc

    async def list_events(
        self,
        *,
        status: Optional[ConnectorEventStatus] = None,
        limit: int = 50,
    ) -> AuditEventListResponse:
        params: dict[str, object] = {"limit": limit}
        if status is not None:
            params["status"] = status.value
        return await self._get(
            self._endpoint,
            AuditEventListResponse,
            params=params,
        )

    async def get_event(
        self,
        event_key: str,
    ) -> Optional[AuditEventDetailResponse]:
        try:
            return await self._get(
                f"{self._endpoint}/{event_key}",
                AuditEventDetailResponse,
            )
        except ReviewLabAdapterError as exc:
            if exc.code == "review_lab_event_not_found":
                return None
            raise

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "HttpReviewLabAdapter":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


class ReviewLabController:
    """Selecciona el evento; jamás modifica el adaptador ni el conector."""

    def __init__(self, adapter: ReviewLabAuditAdapter) -> None:
        self._adapter = adapter

    async def load(
        self,
        *,
        event_key: Optional[str] = None,
        status: Optional[ConnectorEventStatus] = None,
        limit: int = 50,
    ) -> ReviewLabSnapshot:
        events = await self._adapter.list_events(status=status, limit=limit)
        selected_key = event_key
        if selected_key is None and events.items:
            selected_key = events.items[0].event_key
        selected = (
            await self._adapter.get_event(selected_key)
            if selected_key is not None
            else None
        )
        banner = (
            "FIXTURE LOCAL · MODO REAL OFF · SIN CONEXIONES EXTERNAS"
            if self._adapter.source is ReviewLabSource.FIXTURE
            else "AUDITORÍA GET · SOLO LECTURA · ACCIONES DESHABILITADAS"
        )
        return ReviewLabSnapshot(
            source=self._adapter.source,
            banner=banner,
            events=events,
            selected=selected,
        )
