"""Coordinador durable de decisiones sobre una colección Mongo inyectada.

No crea clientes, bases de datos ni conexiones. La colección debe ofrecer el
subconjunto asíncrono de la API de Motor usado por este módulo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from .review_approval import (
    ReviewDecisionCommand,
    ReviewDecisionStage,
    ReviewDecisionValue,
)
from .review_decision_coordinator import (
    ReviewArtifactStatus,
    ReviewDecisionOutcome,
    ReviewDecisionResult,
)


REVIEW_DECISION_ID_INDEX = "ux_review_decision_ids"
REVIEW_DECISION_ID_KEYS = [("review_decision_ids", ASCENDING)]


class AsyncReviewCollection(Protocol):
    async def create_index(self, keys, **options): ...

    async def find_one(self, selector, projection): ...

    async def find_one_and_update(
        self,
        selector,
        update,
        *,
        projection,
        return_document,
    ): ...


_STAGE_FIELDS = {
    ReviewDecisionStage.INPUT: {
        "review": "preflight_review",
        "decision": "input_decision",
        "expected": ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
    },
    ReviewDecisionStage.OUTPUT: {
        "review": "output_review",
        "decision": "output_decision",
        "expected": ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
    },
}

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

_PROJECTION = {
    "_id": 0,
    "event_key": 1,
    "status": 1,
    "preflight_review": 1,
    "input_decision": 1,
    "output_review": 1,
    "output_decision": 1,
    "review_decision_ids": 1,
}


class MongoReviewDecisionCoordinator:
    """Aplica la decisión y su evidencia en una única actualización atómica."""

    def __init__(
        self,
        collection: AsyncReviewCollection,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._collection = collection
        self._clock = clock

    async def ensure_indexes(self) -> str:
        """Crea solo el índice requerido, cuando el compositor lo solicite."""

        return await self._collection.create_index(
            REVIEW_DECISION_ID_KEYS,
            name=REVIEW_DECISION_ID_INDEX,
            unique=True,
            sparse=True,
        )

    async def decide(self, command: ReviewDecisionCommand) -> ReviewDecisionResult:
        fingerprint = command.semantic_fingerprint()
        decision_id = str(command.decision_id)

        existing = await self._find_by_decision_id(decision_id)
        if existing is not None:
            return self._existing_result(command, fingerprint, existing)

        observed_at = self._now()
        fields = _STAGE_FIELDS[command.stage]
        target = _TARGET_STATUS[(command.stage, command.decision)]
        review_field = fields["review"]
        decision_field = fields["decision"]

        decision_document = {
            "decision_id": decision_id,
            "semantic_fingerprint": fingerprint,
            "stage": command.stage.value,
            "action": command.action.value,
            "decision": command.decision.value,
            "content_hash": command.content_hash,
            "actor": command.principal.actor,
            "credential_id": command.principal.credential_id,
            "reason": command.reason,
            "status_before": command.expected_status.value,
            "status_after": target.value,
            "decided_at": observed_at,
        }
        selector: dict[str, Any] = {
            "event_key": command.event_key,
            "status": command.expected_status.value,
            f"{review_field}.content_hash": command.content_hash,
            decision_field: None,
            "review_decision_ids": {"$ne": decision_id},
        }
        if command.decision is ReviewDecisionValue.APPROVED:
            selector[f"{review_field}.decision"] = "ready_for_review"

        try:
            updated = await self._collection.find_one_and_update(
                selector,
                {
                    "$set": {
                        "status": target.value,
                        "updated_at": observed_at,
                        decision_field: decision_document,
                    },
                    "$addToSet": {"review_decision_ids": decision_id},
                },
                projection=_PROJECTION,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            updated = None

        if updated is not None:
            return self._applied_result(command, decision_document, idempotent=False)

        existing = await self._find_by_decision_id(decision_id)
        if existing is not None:
            return self._existing_result(command, fingerprint, existing)
        return await self._classify_failed_precondition(command, observed_at)

    async def _find_by_decision_id(self, decision_id: str):
        return await self._collection.find_one(
            {"review_decision_ids": decision_id},
            _PROJECTION,
        )

    def _existing_result(
        self,
        command: ReviewDecisionCommand,
        fingerprint: str,
        document: dict[str, Any],
    ) -> ReviewDecisionResult:
        stored = self._stored_decision(document, str(command.decision_id))
        if stored is None or stored.get("semantic_fingerprint") != fingerprint:
            return self._failure_result(
                command,
                ReviewDecisionOutcome.IDEMPOTENCY_CONFLICT,
                document=document,
            )
        return self._applied_result(command, stored, idempotent=True)

    async def _classify_failed_precondition(
        self,
        command: ReviewDecisionCommand,
        observed_at: datetime,
    ) -> ReviewDecisionResult:
        document = await self._collection.find_one(
            {"event_key": command.event_key},
            _PROJECTION,
        )
        if document is None:
            return self._failure_result(
                command,
                ReviewDecisionOutcome.NOT_FOUND,
                observed_at=observed_at,
            )

        fields = _STAGE_FIELDS[command.stage]
        if document.get(fields["decision"]) is not None:
            outcome = ReviewDecisionOutcome.ALREADY_DECIDED
        elif document.get("status") != command.expected_status.value:
            outcome = ReviewDecisionOutcome.STATUS_MISMATCH
        else:
            review = document.get(fields["review"]) or {}
            if review.get("content_hash") != command.content_hash:
                outcome = ReviewDecisionOutcome.STALE_HASH
            elif (
                command.decision is ReviewDecisionValue.APPROVED
                and review.get("decision") != "ready_for_review"
            ):
                outcome = ReviewDecisionOutcome.ARTIFACT_BLOCKED
            else:
                outcome = ReviewDecisionOutcome.STATUS_MISMATCH
        return self._failure_result(
            command,
            outcome,
            document=document,
            observed_at=observed_at,
        )

    @staticmethod
    def _stored_decision(
        document: dict[str, Any],
        decision_id: str,
    ) -> dict[str, Any] | None:
        for field in ("input_decision", "output_decision"):
            stored = document.get(field)
            if isinstance(stored, dict) and stored.get("decision_id") == decision_id:
                return stored
        return None

    def _applied_result(
        self,
        command: ReviewDecisionCommand,
        stored: dict[str, Any],
        *,
        idempotent: bool,
    ) -> ReviewDecisionResult:
        try:
            observed_at = stored["decided_at"]
            if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
                raise ValueError
            status_before = ReviewArtifactStatus(stored["status_before"])
            status_after = ReviewArtifactStatus(stored["status_after"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("review_decision_document_invalid") from error
        return ReviewDecisionResult(
            outcome=ReviewDecisionOutcome.APPLIED,
            idempotent=idempotent,
            event_key=command.event_key,
            stage=command.stage,
            decision_id=command.decision_id,
            status_before=status_before,
            status_after=status_after,
            content_hash=stored["content_hash"],
            actor=stored["actor"],
            observed_at=observed_at,
        )

    def _failure_result(
        self,
        command: ReviewDecisionCommand,
        outcome: ReviewDecisionOutcome,
        *,
        document: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
    ) -> ReviewDecisionResult:
        status = None
        if document is not None:
            try:
                status = ReviewArtifactStatus(document.get("status"))
            except ValueError:
                status = None
        return ReviewDecisionResult(
            outcome=outcome,
            event_key=command.event_key,
            stage=command.stage,
            decision_id=command.decision_id,
            status_before=status,
            status_after=status,
            content_hash=command.content_hash,
            actor=command.principal.actor,
            observed_at=observed_at or self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("review_decision_clock_invalid")
        return value.astimezone(timezone.utc)
