"""Modelos allowlist para observar el conector sin habilitar acciones."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .modes import ConnectorMode
from .models import ConnectorEventStatus
from .nia_client import NiaChatResponse
from .output_review import BitrixMessagePayloadPreview, OutputReview
from .preflight import (
    NiaTextPayloadPreview,
    PreflightManifest,
    PreflightNormalizedInput,
    TextPreflightReview,
)
from .workflow_policy import WorkflowGuard


class AuditSafetyState(BaseModel):
    """Distingue la seguridad real del escenario que solo se representa."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["local_simulation"] = "local_simulation"
    real_effective_mode: Literal[ConnectorMode.OFF] = ConnectorMode.OFF
    scenario_mode: ConnectorMode
    activation_locked: Literal[True] = True
    external_calls_enabled: Literal[False] = False
    real_connections_used: Literal[False] = False
    bitrix_write_performed: Literal[False] = False


class AuditDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal["input", "output"]
    decision: str = Field(min_length=1)
    source: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class AuditTimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str = Field(min_length=1)
    status: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class AuditEventView(BaseModel):
    """Vista explícita; no devuelve el documento Mongo arbitrario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    simulation: Literal[True] = True
    title: str = Field(min_length=1)
    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["shadowed"] = "shadowed"
    received_at: datetime
    updated_at: datetime
    safety: AuditSafetyState
    original_event_redacted: dict[str, Any]
    normalized_message: PreflightNormalizedInput
    attachment_manifest: PreflightManifest
    nia_payload: NiaTextPayloadPreview
    input_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_decision: AuditDecision
    nia_response: NiaChatResponse
    bitrix_payload_preview: BitrixMessagePayloadPreview
    output_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_decision: AuditDecision
    workflow_guard: WorkflowGuard
    shadow_result: dict[str, Any]
    outbound_message_id: Optional[int] = None
    timeline: tuple[AuditTimelineItem, ...]

    @model_validator(mode="after")
    def validate_inert_shadow_view(self) -> "AuditEventView":
        if self.safety.scenario_mode is not ConnectorMode.SHADOW:
            raise ValueError("review_lab_requires_shadow_scenario")
        if self.workflow_guard.bitrix_send_allowed:
            raise ValueError("shadow_view_cannot_allow_bitrix")
        if self.outbound_message_id is not None:
            raise ValueError("shadow_view_cannot_have_outbound_message")
        return self


class AuditStoredDecision(BaseModel):
    """Decisión persistida sin campos arbitrarios del documento interno."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: str = Field(min_length=1)
    source: Optional[str] = None
    effective_mode: Optional[ConnectorMode] = None
    content_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    actor: Optional[str] = None
    reason: Optional[str] = None
    decided_at: Optional[datetime] = None


class AuditShadowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=1)
    effective_mode: ConnectorMode
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_at: Optional[datetime] = None


class AuditAttemptCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    processing: int = Field(ge=0)
    nia: int = Field(ge=0)
    bitrix: int = Field(ge=0)


class AuditEventListItem(BaseModel):
    """Resumen sin texto del cliente ni cuerpos de respuesta."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ConnectorEventStatus
    received_at: datetime
    updated_at: datetime
    message_id: Optional[int] = Field(default=None, gt=0)
    dialog_id: Optional[str] = None
    observed_mode: ConnectorMode
    has_nia_response: bool
    has_bitrix_preview: bool
    bitrix_written: bool


class AuditEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[AuditEventListItem, ...]
    returned: int = Field(ge=0)


class AuditEventDetailResponse(BaseModel):
    """Detalle GET completo, separado del modelo Mongo y sin secretos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ConnectorEventStatus
    received_at: datetime
    updated_at: datetime
    identity_verified: bool
    security_reason: str
    original_event_redacted: dict[str, Any]
    normalized_message: Optional[PreflightNormalizedInput] = None
    attachment_manifest: Optional[PreflightManifest] = None
    nia_payload: Optional[NiaTextPayloadPreview] = None
    input_content_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    input_decision: Optional[AuditStoredDecision] = None
    nia_response: Optional[NiaChatResponse] = None
    bitrix_payload_preview: Optional[BitrixMessagePayloadPreview] = None
    output_content_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    output_decision: Optional[AuditStoredDecision] = None
    workflow_guard: WorkflowGuard
    shadow_result: Optional[AuditShadowResult] = None
    outbound_message_id: Optional[int] = Field(default=None, gt=0)
    attempts: AuditAttemptCounts
    processing_stage: Optional[str] = None
    last_error: Optional[str] = None


def build_audit_event_view(
    *,
    title: str,
    received_at: datetime,
    updated_at: datetime,
    preflight: TextPreflightReview,
    output: OutputReview,
    guard: WorkflowGuard,
) -> AuditEventView:
    """Compone la vista simulada usando los contratos reales del flujo."""

    if preflight.event_key != output.event_key:
        raise ValueError("audit_event_key_mismatch")
    if preflight.nia_payload_preview is None:
        raise ValueError("audit_requires_ready_nia_payload")

    return AuditEventView(
        title=title,
        event_key=preflight.event_key,
        received_at=received_at,
        updated_at=updated_at,
        safety=AuditSafetyState(scenario_mode=ConnectorMode.SHADOW),
        original_event_redacted=preflight.raw_redacted,
        normalized_message=preflight.normalized_input,
        attachment_manifest=preflight.preflight_manifest,
        nia_payload=preflight.nia_payload_preview,
        input_content_hash=preflight.content_hash,
        input_decision=AuditDecision(
            stage="input",
            decision="approved_for_simulation",
            source="fixture",
            reason="local_shadow_scenario",
        ),
        nia_response=output.nia_response,
        bitrix_payload_preview=output.bitrix_payload_preview,
        output_content_hash=output.content_hash,
        output_decision=AuditDecision(
            stage="output",
            decision="suppressed",
            source="mode_policy",
            reason="bitrix_suppressed_by_shadow",
        ),
        workflow_guard=guard,
        shadow_result={
            "status": "shadowed",
            "effective_mode": "shadow",
            "reason": "bitrix_suppressed_by_shadow",
            "content_hash": output.content_hash,
            "bitrix_attempt_count": 0,
        },
        timeline=(
            AuditTimelineItem(
                stage="received",
                status="verified",
                detail="Evento ficticio recibido y secretos redactados.",
            ),
            AuditTimelineItem(
                stage="preflight",
                status="ready",
                detail="Texto normalizado y payload exacto preparados.",
            ),
            AuditTimelineItem(
                stage="nia",
                status="simulated",
                detail="Respuesta producida por un doble local de NIA.",
            ),
            AuditTimelineItem(
                stage="bitrix",
                status="suppressed",
                detail="Salida visible, pero no enviada por el escenario shadow.",
            ),
        ),
    )
