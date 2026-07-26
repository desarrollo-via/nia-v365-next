"""Composición aislada de la superficie objetivo de decisiones de revisión."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter

from .durable_review_decision_coordinator import (
    AsyncReviewCollection,
    MongoReviewDecisionCoordinator,
)
from .review_approval import ReviewDecisionAction
from .review_auth import SingleReviewerAuthenticator
from .review_decision_audit import (
    AsyncReviewAuditCollection,
    MongoReviewDecisionAuditStore,
)
from .review_decision_http import build_review_decision_router
from .review_decision_service import InMemoryReviewDecisionService


@dataclass(frozen=True)
class ReviewDecisionIndexNames:
    decision: str
    audit: tuple[str, str]


@dataclass(frozen=True)
class ReviewDecisionResources:
    coordinator: MongoReviewDecisionCoordinator
    audit_store: MongoReviewDecisionAuditStore
    authenticator: SingleReviewerAuthenticator
    service: InMemoryReviewDecisionService
    router: APIRouter

    async def initialize_indexes(self) -> ReviewDecisionIndexNames:
        """Inicializa índices solo bajo una llamada explícita del compositor."""

        decision = await self.coordinator.ensure_indexes()
        audit = await self.audit_store.ensure_indexes()
        return ReviewDecisionIndexNames(decision=decision, audit=audit)


def compose_review_decision_resources(
    *,
    event_collection: AsyncReviewCollection,
    audit_collection: AsyncReviewAuditCollection,
    review_token: Optional[str],
    actor: Optional[str],
    credential_id: Optional[str],
    allowed_actions: Iterable[ReviewDecisionAction],
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    request_id_factory: Callable[[], UUID] = uuid4,
) -> ReviewDecisionResources:
    """Conecta dependencias ya provistas sin abrirlas, inspeccionarlas o usarlas."""

    if event_collection is audit_collection:
        raise ValueError("review_event_and_audit_collections_must_differ")

    coordinator = MongoReviewDecisionCoordinator(event_collection, clock=clock)
    audit_store = MongoReviewDecisionAuditStore(audit_collection)
    authenticator = SingleReviewerAuthenticator(
        review_token=review_token,
        actor=actor,
        credential_id=credential_id,
        clock=clock,
    )
    service = InMemoryReviewDecisionService(
        authenticator=authenticator,
        coordinator=coordinator,
        audit_sink=audit_store,
        allowed_actions=allowed_actions,
        request_id_factory=request_id_factory,
    )
    return ReviewDecisionResources(
        coordinator=coordinator,
        audit_store=audit_store,
        authenticator=authenticator,
        service=service,
        router=build_review_decision_router(service),
    )
