"""Auditoría segura e inyectable de intentos humanos de revisión."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ASCENDING, DESCENDING

from .review_approval import (
    ReviewDecisionAction,
    ReviewDecisionStage,
    ReviewDecisionValue,
)
from .review_decision_coordinator import (
    ReviewArtifactStatus,
    ReviewDecisionOutcome,
)


REVIEW_AUDIT_REQUEST_INDEX = "ux_review_audit_request_id"
REVIEW_AUDIT_DECISION_TIME_INDEX = "idx_review_audit_decision_time"
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|token|password|secret)\b\s*[:=]\s*\S+"
    r"|\bbearer\s+\S+)"
)


class ReviewDecisionAuditAttempt(BaseModel):
    """Registro allowlisted; nunca conserva autorización ni cuerpo original."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    recorded_at: datetime
    actor: str = Field(min_length=1, max_length=100)
    credential_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,100}$")
    event_key: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    action: Optional[ReviewDecisionAction] = None
    stage: Optional[ReviewDecisionStage] = None
    decision: Optional[ReviewDecisionValue] = None
    decision_id: Optional[UUID] = None
    content_hash: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reason: Optional[str] = Field(default=None, max_length=500)
    service_code: str = Field(pattern=r"^review_[a-z0-9_]+$")
    status_code: int = Field(ge=100, le=599)
    coordinator_outcome: Optional[ReviewDecisionOutcome] = None
    idempotent: Optional[bool] = None
    status_before: Optional[ReviewArtifactStatus] = None
    status_after: Optional[ReviewArtifactStatus] = None

    @field_validator("request_id")
    @classmethod
    def request_id_is_v4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("request_id debe ser UUID v4")
        return value

    @field_validator("actor")
    @classmethod
    def actor_is_safe(cls, value: str) -> str:
        clean = value.strip()
        if not clean or any(
            ord(character) < 32 or ord(character) == 127 for character in clean
        ):
            raise ValueError("actor de auditoría inválido")
        return clean

    @field_validator("reason")
    @classmethod
    def reason_is_safe(cls, value: Optional[str]) -> Optional[str]:
        clean = (value or "").strip()
        if not clean:
            return None
        if _SECRET_VALUE_PATTERN.search(clean):
            raise ValueError("reason de auditoría no admite secretos")
        return clean

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("recorded_at debe incluir zona horaria")
        return value.astimezone(timezone.utc)


class ReviewDecisionAuditSink(Protocol):
    async def record(self, attempt: ReviewDecisionAuditAttempt) -> None: ...


class InMemoryReviewDecisionAuditStore:
    """Almacén hermético para composición y pruebas sin dependencias externas."""

    def __init__(self) -> None:
        self.attempts: dict[UUID, ReviewDecisionAuditAttempt] = {}

    async def record(self, attempt: ReviewDecisionAuditAttempt) -> None:
        existing = self.attempts.get(attempt.request_id)
        if existing is not None and existing != attempt:
            raise ValueError("review_audit_request_id_conflict")
        self.attempts[attempt.request_id] = attempt


class AsyncReviewAuditCollection(Protocol):
    async def create_index(self, keys, **options): ...

    async def update_one(self, selector, update, *, upsert): ...

    async def find_one(self, selector, projection): ...


class MongoReviewDecisionAuditStore:
    """Persistencia Mongo-compatible; la colección y sus recursos son externos."""

    def __init__(self, collection: AsyncReviewAuditCollection) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> tuple[str, str]:
        request_index = await self._collection.create_index(
            [("request_id", ASCENDING)],
            name=REVIEW_AUDIT_REQUEST_INDEX,
            unique=True,
        )
        decision_index = await self._collection.create_index(
            [("decision_id", ASCENDING), ("recorded_at", DESCENDING)],
            name=REVIEW_AUDIT_DECISION_TIME_INDEX,
            sparse=True,
        )
        return request_index, decision_index

    async def record(self, attempt: ReviewDecisionAuditAttempt) -> None:
        document = _audit_document(attempt)
        result = await self._collection.update_one(
            {"request_id": document["request_id"]},
            {"$setOnInsert": document},
            upsert=True,
        )
        if result.upserted_id is not None:
            return
        existing = await self._collection.find_one(
            {"request_id": document["request_id"]},
            {"_id": 0},
        )
        if existing != document:
            raise ValueError("review_audit_request_id_conflict")


def _audit_document(attempt: ReviewDecisionAuditAttempt) -> dict[str, Any]:
    document = attempt.model_dump(mode="python")
    document["request_id"] = str(attempt.request_id)
    document["decision_id"] = (
        str(attempt.decision_id) if attempt.decision_id is not None else None
    )
    for field in (
        "action",
        "stage",
        "decision",
        "coordinator_outcome",
        "status_before",
        "status_after",
    ):
        value = document[field]
        document[field] = value.value if value is not None else None
    return document
