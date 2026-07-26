"""Coordinador hermético e idempotente de decisiones de revisión.

Este módulo conserva artefactos y resultados solo en memoria. No está conectado
al router, MongoDB, los workers ni clientes externos.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Iterable, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .review_approval import (
    ReviewDecisionCommand,
    ReviewDecisionStage,
    ReviewDecisionValue,
)


class ReviewArtifactStatus(str, Enum):
    NEEDS_INPUT_REVIEW = "needs_input_review"
    READY_FOR_NIA = "ready_for_nia"
    INPUT_REJECTED = "input_rejected"
    NEEDS_OUTPUT_REVIEW = "needs_output_review"
    READY_FOR_BITRIX = "ready_for_bitrix"
    OUTPUT_REJECTED = "output_rejected"


class ReviewDecisionOutcome(str, Enum):
    APPLIED = "applied"
    NOT_FOUND = "not_found"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    STALE_HASH = "stale_hash"
    STATUS_MISMATCH = "status_mismatch"
    ALREADY_DECIDED = "already_decided"
    ARTIFACT_BLOCKED = "artifact_blocked"


class ReviewableArtifact(BaseModel):
    """Instantánea inmutable de un artefacto sujeto a revisión."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage: ReviewDecisionStage
    status: ReviewArtifactStatus
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_id: Optional[UUID] = None
    decision: Optional[ReviewDecisionValue] = None
    actor: Optional[str] = None
    decided_at: Optional[datetime] = None

    @field_validator("decided_at")
    @classmethod
    def normalize_decided_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("decided_at debe incluir zona horaria")
        return value.astimezone(timezone.utc)


class ReviewDecisionResult(BaseModel):
    """Resultado estable de una intención; ``idempotent`` marca un replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReviewDecisionOutcome
    idempotent: bool = False
    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage: ReviewDecisionStage
    decision_id: UUID
    status_before: Optional[ReviewArtifactStatus] = None
    status_after: Optional[ReviewArtifactStatus] = None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: str
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at debe incluir zona horaria")
        return value.astimezone(timezone.utc)


_TARGET_STATUS = {
    (ReviewDecisionStage.INPUT, ReviewDecisionValue.APPROVED): (
        ReviewArtifactStatus.READY_FOR_NIA
    ),
    (ReviewDecisionStage.INPUT, ReviewDecisionValue.REJECTED): (
        ReviewArtifactStatus.INPUT_REJECTED
    ),
    (ReviewDecisionStage.OUTPUT, ReviewDecisionValue.APPROVED): (
        ReviewArtifactStatus.READY_FOR_BITRIX
    ),
    (ReviewDecisionStage.OUTPUT, ReviewDecisionValue.REJECTED): (
        ReviewArtifactStatus.OUTPUT_REJECTED
    ),
}


class InMemoryReviewDecisionCoordinator:
    """Serializa decisiones y conserva su resultado por ``decision_id``."""

    def __init__(
        self,
        artifacts: Iterable[ReviewableArtifact],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._artifacts: dict[
            tuple[str, ReviewDecisionStage], ReviewableArtifact
        ] = {}
        for artifact in artifacts:
            key = (artifact.event_key, artifact.stage)
            if key in self._artifacts:
                raise ValueError("review_artifact_duplicate")
            self._artifacts[key] = artifact
        self._decisions: dict[UUID, tuple[str, ReviewDecisionResult]] = {}
        self._clock = clock
        self._lock = asyncio.Lock()

    def get_artifact(
        self,
        event_key: str,
        stage: ReviewDecisionStage,
    ) -> Optional[ReviewableArtifact]:
        """Devuelve la instantánea actual; el modelo retornado es inmutable."""

        return self._artifacts.get((event_key, ReviewDecisionStage(stage)))

    async def decide(self, command: ReviewDecisionCommand) -> ReviewDecisionResult:
        """Aplica o reproduce una decisión sin efectos fuera de esta instancia."""

        fingerprint = command.semantic_fingerprint()
        async with self._lock:
            prior = self._decisions.get(command.decision_id)
            if prior is not None:
                prior_fingerprint, prior_result = prior
                if prior_fingerprint == fingerprint:
                    return prior_result.model_copy(update={"idempotent": True})
                return self._result(
                    command,
                    ReviewDecisionOutcome.IDEMPOTENCY_CONFLICT,
                    artifact=self._artifacts.get((command.event_key, command.stage)),
                )

            artifact_key = (command.event_key, command.stage)
            artifact = self._artifacts.get(artifact_key)
            if artifact is None:
                return self._remember(
                    fingerprint,
                    command,
                    ReviewDecisionOutcome.NOT_FOUND,
                    artifact=None,
                )
            if artifact.decision_id is not None:
                return self._remember(
                    fingerprint,
                    command,
                    ReviewDecisionOutcome.ALREADY_DECIDED,
                    artifact=artifact,
                )
            if artifact.status.value != command.expected_status.value:
                return self._remember(
                    fingerprint,
                    command,
                    ReviewDecisionOutcome.STATUS_MISMATCH,
                    artifact=artifact,
                )
            if artifact.content_hash != command.content_hash:
                return self._remember(
                    fingerprint,
                    command,
                    ReviewDecisionOutcome.STALE_HASH,
                    artifact=artifact,
                )

            observed_at = self._now()
            target_status = _TARGET_STATUS[(command.stage, command.decision)]
            updated = artifact.model_copy(
                update={
                    "status": target_status,
                    "decision_id": command.decision_id,
                    "decision": command.decision,
                    "actor": command.principal.actor,
                    "decided_at": observed_at,
                }
            )
            self._artifacts[artifact_key] = updated
            result = ReviewDecisionResult(
                outcome=ReviewDecisionOutcome.APPLIED,
                event_key=command.event_key,
                stage=command.stage,
                decision_id=command.decision_id,
                status_before=artifact.status,
                status_after=target_status,
                content_hash=command.content_hash,
                actor=command.principal.actor,
                observed_at=observed_at,
            )
            self._decisions[command.decision_id] = (fingerprint, result)
            return result

    def _remember(
        self,
        fingerprint: str,
        command: ReviewDecisionCommand,
        outcome: ReviewDecisionOutcome,
        *,
        artifact: Optional[ReviewableArtifact],
    ) -> ReviewDecisionResult:
        result = self._result(command, outcome, artifact=artifact)
        self._decisions[command.decision_id] = (fingerprint, result)
        return result

    def _result(
        self,
        command: ReviewDecisionCommand,
        outcome: ReviewDecisionOutcome,
        *,
        artifact: Optional[ReviewableArtifact],
    ) -> ReviewDecisionResult:
        status = artifact.status if artifact is not None else None
        return ReviewDecisionResult(
            outcome=outcome,
            event_key=command.event_key,
            stage=command.stage,
            decision_id=command.decision_id,
            status_before=status,
            status_after=status,
            content_hash=command.content_hash,
            actor=command.principal.actor,
            observed_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("review_decision_clock_invalid")
        return value.astimezone(timezone.utc)
