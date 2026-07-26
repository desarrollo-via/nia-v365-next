"""Procesamiento HTTP inyectable del webhook de Bitrix24."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional, Protocol

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import ConnectorMode, ConnectorSettings
from .event_parser import parse_webhook_form
from .idempotency import build_event_key
from .models import (
    ConnectorIngestionStatus,
    WebhookEventSummary,
    WebhookReceipt,
)
from .runtime import ConnectorRuntimeUnavailable
from .security import redact_form_data, validate_webhook_identity
from .service import ConnectorPersistenceError


class WebhookRuntime(Protocol):
    async def ingest(
        self,
        raw_form: dict[str, object],
        settings: ConnectorSettings,
    ): ...


async def handle_bitrix_webhook(
    request: Request,
    *,
    settings_loader: Callable[[], ConnectorSettings],
    runtime: Optional[WebhookRuntime] = None,
) -> WebhookReceipt | JSONResponse:
    """Valida el formulario y solo persiste si existe un runtime habilitado."""

    try:
        incoming_form = await request.form()
        flat_form = {
            str(key): value for key, value in incoming_form.multi_items()
        }
        redacted = redact_form_data(flat_form)
        event = parse_webhook_form(flat_form)
    except (TypeError, ValueError, ValidationError):
        return JSONResponse(
            status_code=400,
            content={
                "status": "invalid",
                "reason": "invalid_webhook_payload",
                "persisted": False,
                "nia_called": False,
                "bitrix_written": False,
            },
        )

    settings = settings_loader()
    security = validate_webhook_identity(event, settings)
    supported_event = event.event == "ONIMBOTV2MESSAGEADD"
    event_key = build_event_key(event)
    duplicate_detection = "not_persisted"
    persisted = False
    http_status = 200

    if not supported_event:
        status = "ignored"
        reason = "unsupported_event"
    elif not security.accepted:
        status = "ignored"
        reason = security.reason
    elif settings.activation_locked or settings.effective_mode is ConnectorMode.OFF:
        status = "disabled"
        reason = "connector_locked_off"
    elif runtime is None:
        status = "disabled"
        reason = "connector_runtime_not_ready"
    else:
        try:
            ingestion = await runtime.ingest(flat_form, settings)
        except ConnectorRuntimeUnavailable:
            status = "disabled"
            reason = "connector_runtime_not_ready"
        except ConnectorPersistenceError:
            status = "retryable_error"
            reason = "connector_storage_unavailable"
            http_status = 503
        else:
            event_key = ingestion.event_key or event_key
            if ingestion.status is ConnectorIngestionStatus.STORED:
                status = "stored"
                reason = ingestion.reason
                duplicate_detection = "unique_created"
                persisted = True
            elif ingestion.status is ConnectorIngestionStatus.DUPLICATE:
                status = "duplicate"
                reason = ingestion.reason
                duplicate_detection = "duplicate"
                persisted = True
            else:
                status = ingestion.status.value
                reason = ingestion.reason

    receipt = WebhookReceipt(
        status=status,
        reason=reason,
        effective_mode=settings.effective_mode.value,
        event_key=event_key,
        identity_verified=security.accepted,
        redacted_secret_fields=sum(
            value == "[REDACTED]" for value in redacted.values()
        ),
        duplicate_detection=duplicate_detection,
        persisted=persisted,
        nia_called=False,
        bitrix_written=False,
        event_summary=WebhookEventSummary(
            event=event.event,
            bot_id=event.bot_id,
            message_id=event.message_id,
            chat_id=event.chat_id,
            dialog_id=event.dialog_id,
            text_length=len(event.text),
            is_system=event.is_system,
        ),
    )
    if http_status == 503:
        return JSONResponse(
            status_code=http_status,
            headers={"Retry-After": "5"},
            content=receipt.model_dump(),
        )
    return receipt


__all__ = ["WebhookRuntime", "handle_bitrix_webhook"]
