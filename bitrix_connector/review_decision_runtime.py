"""Ciclo de vida fail-closed para las decisiones administrativas de revisión."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from .config import ConnectorMode, ConnectorSettings
from .review_approval import ReviewDecisionAction
from .review_auth import SingleReviewerAuthenticator
from .review_decision_composition import (
    ReviewDecisionResources,
    compose_review_decision_resources,
)
from .review_decision_service import ReviewDecisionServiceResponse


class ReviewDecisionRuntimeState(str, Enum):
    STOPPED = "stopped"
    INERT = "inert"
    READY = "ready"


@dataclass(frozen=True)
class ReviewDecisionRuntimeSnapshot:
    state: ReviewDecisionRuntimeState
    resources_available: bool
    failure_code: Optional[str] = None


class ReviewDecisionRuntime:
    """Posee Mongo y la composición objetivo sin comprometer el arranque de NIA."""

    def __init__(
        self,
        *,
        mongo_client_factory: Any = AsyncIOMotorClient,
        composition_factory: Callable[..., ReviewDecisionResources] = (
            compose_review_decision_resources
        ),
    ) -> None:
        self._mongo_client_factory = mongo_client_factory
        self._composition_factory = composition_factory
        self._lock = asyncio.Lock()
        self._state = ReviewDecisionRuntimeState.STOPPED
        self._failure_code: Optional[str] = None
        self._mongo_client: Any = None
        self._resources: Optional[ReviewDecisionResources] = None

    @property
    def snapshot(self) -> ReviewDecisionRuntimeSnapshot:
        return ReviewDecisionRuntimeSnapshot(
            state=self._state,
            resources_available=self._resources is not None,
            failure_code=self._failure_code,
        )

    async def start(
        self,
        settings: ConnectorSettings,
    ) -> ReviewDecisionRuntimeSnapshot:
        async with self._lock:
            if self._state is not ReviewDecisionRuntimeState.STOPPED:
                return self.snapshot

            if (
                settings.activation_locked
                or settings.effective_mode is ConnectorMode.OFF
                or not settings.external_calls_enabled
            ):
                return self._mark_inert("review_safety_barrier_active")

            configuration = self._validated_configuration(settings)
            if configuration is None:
                return self._mark_inert("review_configuration_invalid")
            (
                mongo_uri,
                mongo_db,
                events_collection,
                audit_collection,
            ) = configuration

            mongo_client = None
            try:
                mongo_client = self._mongo_client_factory(
                    mongo_uri,
                    connect=False,
                )
                database = mongo_client[mongo_db]
                resources = self._composition_factory(
                    event_collection=database[events_collection],
                    audit_collection=database[audit_collection],
                    review_token=settings.review_token,
                    actor=settings.review_actor,
                    credential_id=settings.review_credential_id,
                    allowed_actions=tuple(ReviewDecisionAction),
                )
                await resources.initialize_indexes()
            except Exception:
                self._close_client(mongo_client)
                return self._mark_inert("review_resources_unavailable")
            except BaseException:
                self._close_client(mongo_client)
                raise

            self._mongo_client = mongo_client
            self._resources = resources
            self._state = ReviewDecisionRuntimeState.READY
            self._failure_code = None
            return self.snapshot

    async def handle_lazy_payload(
        self,
        *,
        authorization: str,
        event_key: str,
        action: object,
        payload_loader,
    ) -> ReviewDecisionServiceResponse:
        async with self._lock:
            resources = self._resources
            if self._state is not ReviewDecisionRuntimeState.READY or resources is None:
                return ReviewDecisionServiceResponse(
                    status_code=503,
                    code="review_runtime_unavailable",
                )
            return await resources.service.handle_lazy_payload(
                authorization=authorization,
                event_key=event_key,
                action=action,
                payload_loader=payload_loader,
            )

    async def close(self) -> ReviewDecisionRuntimeSnapshot:
        async with self._lock:
            mongo_client = self._mongo_client
            self._mongo_client = None
            self._resources = None
            self._state = ReviewDecisionRuntimeState.STOPPED
            self._failure_code = None
            self._close_client(mongo_client)
            return self.snapshot

    def _validated_configuration(
        self,
        settings: ConnectorSettings,
    ) -> Optional[tuple[str, str, str, str]]:
        mongo_uri = self._clean(settings.mongo_uri)
        mongo_db = self._clean(settings.mongo_db)
        events_collection = self._clean(settings.events_collection)
        audit_collection = self._clean(settings.review_audit_collection)
        if not all((mongo_uri, mongo_db, events_collection, audit_collection)):
            return None
        if events_collection == audit_collection:
            return None
        authenticator = SingleReviewerAuthenticator(
            review_token=settings.review_token,
            actor=settings.review_actor,
            credential_id=settings.review_credential_id,
        )
        if not authenticator.configured:
            return None
        return mongo_uri, mongo_db, events_collection, audit_collection

    def _mark_inert(self, failure_code: str) -> ReviewDecisionRuntimeSnapshot:
        self._state = ReviewDecisionRuntimeState.INERT
        self._failure_code = failure_code
        self._mongo_client = None
        self._resources = None
        return self.snapshot

    @staticmethod
    def _clean(value: Optional[str]) -> str:
        return (value or "").strip()

    @staticmethod
    def _close_client(client: Any) -> None:
        if client is None:
            return
        try:
            client.close()
        except Exception:
            pass
