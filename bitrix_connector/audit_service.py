"""Lectura allowlist de eventos auditables mediante un almacén inyectado."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .audit import (
    AuditAttemptCounts,
    AuditEventDetailResponse,
    AuditEventListItem,
    AuditEventListResponse,
    AuditShadowResult,
    AuditStoredDecision,
)
from .models import ConnectorEventStatus
from .nia_client import NiaChatResponse
from .output_review import OutputReview
from .preflight import TextPreflightReview
from .security import redact_form_data
from .workflow_policy import WorkflowGuard


class AuditStore(Protocol):
    async def list_audit_events(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    async def get_audit_event(
        self,
        event_key: str,
    ) -> Optional[dict[str, Any]]: ...


class AuditDocumentInvalid(RuntimeError):
    """El documento persistido no cumple los contratos auditables."""


ModelT = TypeVar("ModelT", bound=BaseModel)


def _optional_model(model: type[ModelT], value: Any) -> Optional[ModelT]:
    return None if value is None else model.model_validate(value)


def _guard(document: Mapping[str, Any]) -> WorkflowGuard:
    return WorkflowGuard.model_validate(document.get("workflow_guard"))


def _preflight(document: Mapping[str, Any]) -> Optional[TextPreflightReview]:
    return _optional_model(TextPreflightReview, document.get("preflight_review"))


def _output(document: Mapping[str, Any]) -> Optional[OutputReview]:
    return _optional_model(OutputReview, document.get("output_review"))


def _event_status(value: Any) -> ConnectorEventStatus:
    if isinstance(value, ConnectorEventStatus):
        return value
    return ConnectorEventStatus(str(value))


def _summary_identity(
    document: Mapping[str, Any],
) -> tuple[Optional[int], Optional[str]]:
    preflight = document.get("preflight_review") or {}
    normalized_input = preflight.get("normalized_input") or {}
    normalized_event = document.get("normalized_event") or {}
    output = document.get("output_review") or {}
    preview = output.get("bitrix_payload_preview") or {}
    message_id = normalized_input.get("message_id")
    if message_id is None:
        message_id = normalized_event.get("message_id")
    dialog_id = normalized_input.get("dialog_id")
    if dialog_id is None:
        dialog_id = normalized_event.get("dialog_id")
    if dialog_id is None:
        dialog_id = preview.get("dialogId")
    return message_id, dialog_id


class ConnectorAuditService:
    """No dispone de métodos de escritura ni crea recursos por sí mismo."""

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    async def list_events(
        self,
        *,
        status: Optional[ConnectorEventStatus] = None,
        limit: int = 50,
    ) -> AuditEventListResponse:
        documents = await self._store.list_audit_events(
            status=status.value if status is not None else None,
            limit=limit,
        )
        items: list[AuditEventListItem] = []
        try:
            for document in documents:
                guard = _guard(document)
                message_id, dialog_id = _summary_identity(document)
                event_status = _event_status(document["status"])
                has_output = bool(
                    (document.get("output_review") or {}).get("content_hash")
                )
                items.append(
                    AuditEventListItem(
                        event_key=document["event_key"],
                        status=event_status,
                        received_at=document["received_at"],
                        updated_at=document["updated_at"],
                        message_id=message_id,
                        dialog_id=dialog_id,
                        observed_mode=guard.last_observed_mode,
                        has_nia_response=has_output,
                        has_bitrix_preview=has_output,
                        bitrix_written=(
                            document.get("outbound_message_id") is not None
                        ),
                    )
                )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise AuditDocumentInvalid("audit_document_invalid") from exc
        return AuditEventListResponse(items=tuple(items), returned=len(items))

    async def get_event(
        self,
        event_key: str,
    ) -> Optional[AuditEventDetailResponse]:
        document = await self._store.get_audit_event(event_key)
        if document is None:
            return None
        try:
            preflight = _preflight(document)
            output = _output(document)
            raw = document.get("raw_redacted")
            if raw is None and preflight is not None:
                raw = preflight.raw_redacted
            if not isinstance(raw, Mapping):
                raise ValueError("audit_raw_event_missing")
            nia_response = _optional_model(
                NiaChatResponse,
                document.get("nia_response"),
            )
            if nia_response is None and output is not None:
                nia_response = output.nia_response
            return AuditEventDetailResponse(
                event_key=document["event_key"],
                status=_event_status(document["status"]),
                received_at=document["received_at"],
                updated_at=document["updated_at"],
                identity_verified=bool(document["identity_verified"]),
                security_reason=str(document["security_reason"]),
                original_event_redacted=redact_form_data(raw),
                normalized_message=(
                    preflight.normalized_input if preflight else None
                ),
                attachment_manifest=(
                    preflight.preflight_manifest if preflight else None
                ),
                nia_payload=(
                    preflight.nia_payload_preview if preflight else None
                ),
                input_content_hash=(
                    preflight.content_hash if preflight else None
                ),
                input_decision=_optional_model(
                    AuditStoredDecision,
                    document.get("input_decision"),
                ),
                nia_response=nia_response,
                bitrix_payload_preview=(
                    output.bitrix_payload_preview if output else None
                ),
                output_content_hash=(
                    output.content_hash if output else None
                ),
                output_decision=_optional_model(
                    AuditStoredDecision,
                    document.get("output_decision"),
                ),
                workflow_guard=_guard(document),
                shadow_result=_optional_model(
                    AuditShadowResult,
                    document.get("shadow_result"),
                ),
                outbound_message_id=document.get("outbound_message_id"),
                attempts=AuditAttemptCounts(
                    processing=int(document.get("attempt_count", 0)),
                    nia=int(document.get("nia_attempt_count", 0)),
                    bitrix=int(document.get("bitrix_attempt_count", 0)),
                ),
                processing_stage=document.get("processing_stage"),
                last_error=document.get("last_error"),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise AuditDocumentInvalid("audit_document_invalid") from exc
