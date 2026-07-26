"""Modelos puros del contrato objetivo de aprobación humana.

No están conectados al router, al runtime ni al almacenamiento actual.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


_EVENT_KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_CREDENTIAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|token|password|secret)\b\s*[:=]\s*\S+"
    r"|\bbearer\s+\S+)"
)


class ReviewDecisionAction(str, Enum):
    APPROVE_INPUT = "approve_input"
    REJECT_INPUT = "reject_input"
    APPROVE_OUTPUT = "approve_output"
    REJECT_OUTPUT = "reject_output"


class ReviewDecisionStage(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class ReviewDecisionValue(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewExpectedStatus(str, Enum):
    NEEDS_INPUT_REVIEW = "needs_input_review"
    NEEDS_OUTPUT_REVIEW = "needs_output_review"


class ReviewPrincipal(BaseModel):
    """Identidad calculada por autenticación del servidor, nunca por el body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: str = Field(min_length=1, max_length=100)
    credential_id: str = Field(min_length=1, max_length=100)
    authenticated_at: datetime

    @field_validator("actor")
    @classmethod
    def clean_actor(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("actor no puede estar vacío")
        if any(ord(character) < 32 or ord(character) == 127 for character in clean):
            raise ValueError("actor no admite caracteres de control")
        return clean

    @field_validator("credential_id")
    @classmethod
    def validate_credential_id(cls, value: str) -> str:
        clean = value.strip()
        if not _CREDENTIAL_ID_PATTERN.fullmatch(clean):
            raise ValueError("credential_id debe ser un identificador no secreto")
        return clean

    @field_validator("authenticated_at")
    @classmethod
    def normalize_authenticated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("authenticated_at debe incluir zona horaria")
        return value.astimezone(timezone.utc)


class ReviewDecisionIntent(BaseModel):
    """Cuerpo objetivo permitido desde el cliente; deliberadamente sin actor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_id: UUID
    expected_status: ReviewExpectedStatus
    confirmation: str = Field(min_length=1, max_length=80)
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("confirmation")
    @classmethod
    def clean_confirmation(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("confirmation no puede estar vacía")
        return clean

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("decision_id debe ser UUID v4")
        return value

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: Optional[str]) -> Optional[str]:
        clean = (value or "").strip()
        if not clean:
            return None
        if _SECRET_VALUE_PATTERN.search(clean):
            raise ValueError("reason no admite secretos")
        return clean


class ReviewDecisionCommand(BaseModel):
    """Intención enlazada a ruta y principal después de autenticar."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: ReviewDecisionAction
    stage: ReviewDecisionStage
    decision: ReviewDecisionValue
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_id: UUID
    expected_status: ReviewExpectedStatus
    confirmation: str
    reason: Optional[str] = None
    principal: ReviewPrincipal

    def semantic_fingerprint(self) -> str:
        """Huella estable del significado; excluye hora de autenticación."""

        material = {
            "event_key": self.event_key,
            "action": self.action.value,
            "stage": self.stage.value,
            "decision": self.decision.value,
            "content_hash": self.content_hash,
            "decision_id": str(self.decision_id),
            "expected_status": self.expected_status.value,
            "confirmation": self.confirmation,
            "reason": self.reason,
            "actor": self.principal.actor,
            "credential_id": self.principal.credential_id,
        }
        canonical = json.dumps(
            material,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


_ACTION_CONTRACT = {
    ReviewDecisionAction.APPROVE_INPUT: (
        ReviewDecisionStage.INPUT,
        ReviewDecisionValue.APPROVED,
        ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
        "APROBAR ENVIO A NIA",
    ),
    ReviewDecisionAction.REJECT_INPUT: (
        ReviewDecisionStage.INPUT,
        ReviewDecisionValue.REJECTED,
        ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
        "RECHAZAR ENTRADA",
    ),
    ReviewDecisionAction.APPROVE_OUTPUT: (
        ReviewDecisionStage.OUTPUT,
        ReviewDecisionValue.APPROVED,
        ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
        "APROBAR ENVIO A BITRIX",
    ),
    ReviewDecisionAction.REJECT_OUTPUT: (
        ReviewDecisionStage.OUTPUT,
        ReviewDecisionValue.REJECTED,
        ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
        "RECHAZAR SALIDA",
    ),
}


def bind_review_decision(
    *,
    event_key: str,
    action: ReviewDecisionAction,
    intent: ReviewDecisionIntent,
    principal: ReviewPrincipal,
) -> ReviewDecisionCommand:
    """Aplica las precondiciones dependientes de la ruta sin efectos externos."""

    clean_event_key = event_key.strip()
    if not _EVENT_KEY_PATTERN.fullmatch(clean_event_key):
        raise ValueError("review_event_key_invalid")

    parsed_action = ReviewDecisionAction(action)
    stage, decision, expected_status, confirmation = _ACTION_CONTRACT[
        parsed_action
    ]
    if intent.expected_status is not expected_status:
        raise ValueError("review_expected_status_mismatch")
    if intent.confirmation != confirmation:
        raise ValueError("review_confirmation_mismatch")
    if decision is ReviewDecisionValue.REJECTED and intent.reason is None:
        raise ValueError("review_rejection_reason_required")

    return ReviewDecisionCommand(
        event_key=clean_event_key,
        action=parsed_action,
        stage=stage,
        decision=decision,
        content_hash=intent.content_hash,
        decision_id=intent.decision_id,
        expected_status=intent.expected_status,
        confirmation=intent.confirmation,
        reason=intent.reason,
        principal=principal,
    )
