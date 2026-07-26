"""Despacho durable del payload aprobado hacia un cliente NIA inyectado."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from pydantic import ValidationError

from .models import ConnectorEventRecord, NormalizedBitrixEvent
from .mode_policy import (
    ExternalAction,
    ExternalCallPolicyProvider,
    current_external_call_policy,
)
from .nia_client import NiaClientDecision, NiaClientResult
from .output_review import build_output_review
from .pilot_scope import (
    PilotScopePolicyProvider,
    disabled_pilot_scope_policy,
)
from .preflight import NiaTextPayloadPreview, build_nia_payload_hash
from .storage import ConnectorEventStore
from .worker import ConnectorHandlerResult
from .workflow_policy import WorkflowDecisionSource


class NiaTextSender(Protocol):
    async def send_approved_text(
        self,
        payload: NiaTextPayloadPreview,
    ) -> NiaClientResult: ...


class NiaDispatchWorkerStore:
    """Adapta las transiciones NIA al contrato ya usado por ConnectorWorker."""

    def __init__(self, store: ConnectorEventStore) -> None:
        self._store = store

    async def claim_next(self, **kwargs):
        return await self._store.claim_ready_for_nia(**kwargs)

    async def retry_claim(self, *args, **kwargs):
        return await self._store.retry_nia_claim(*args, **kwargs)

    async def fail_claim(self, *args, **kwargs):
        return await self._store.fail_nia_claim(*args, **kwargs)

    async def complete_claim(self, *args, **kwargs):
        raise RuntimeError("nia_dispatch_success_requires_atomic_response_save")


class NiaDispatchWorkerHandler:
    """Valida el payload durable, invoca el doble NIA y guarda su respuesta."""

    def __init__(
        self,
        store: ConnectorEventStore,
        nia_client: NiaTextSender,
        *,
        lease_owner: str,
        default_retry_after_seconds: int = 30,
        policy_provider: ExternalCallPolicyProvider = current_external_call_policy,
        pilot_policy_provider: PilotScopePolicyProvider = disabled_pilot_scope_policy,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        owner = lease_owner.strip()
        if not owner:
            raise ValueError("lease_owner no puede estar vacío")
        if default_retry_after_seconds <= 0:
            raise ValueError("default_retry_after_seconds debe ser positivo")

        self._store = store
        self._nia_client = nia_client
        self._lease_owner = owner
        self._default_retry_after_seconds = default_retry_after_seconds
        self._policy_provider = policy_provider
        self._pilot_policy_provider = pilot_policy_provider
        self._clock = clock

    async def handle(self, event: ConnectorEventRecord) -> ConnectorHandlerResult:
        payload = self._approved_payload(event)
        if payload is None:
            return ConnectorHandlerResult.failed("nia_approved_payload_invalid")

        policy = self._policy_provider()
        guard = event.workflow_guard.observe(policy.effective_mode)
        input_decision = event.input_decision or {}
        if (
            guard.requires_input_approval
            and input_decision.get("source")
            == WorkflowDecisionSource.MODE_POLICY.value
        ):
            applied = await self._store.require_input_review(
                event.event_key,
                self._lease_owner,
                workflow_guard=guard,
                now=self._clock(),
            )
            if not applied:
                return ConnectorHandlerResult.lease_lost()
            return ConnectorHandlerResult.applied()

        authorization = policy.authorize(ExternalAction.NIA)
        if not authorization.allowed:
            return ConnectorHandlerResult.retryable(
                authorization.reason,
                retry_after_seconds=self._default_retry_after_seconds,
            )

        pilot_reason = self._pilot_rejection_reason(event)
        if pilot_reason is not None:
            return ConnectorHandlerResult.failed(pilot_reason)

        result = await self._nia_client.send_approved_text(payload)
        if result.decision is NiaClientDecision.RETRY:
            return ConnectorHandlerResult.retryable(
                result.error_code or "nia_retryable_error",
                retry_after_seconds=(
                    result.retry_after_seconds
                    or self._default_retry_after_seconds
                ),
            )
        if result.decision is NiaClientDecision.FAIL:
            return ConnectorHandlerResult.failed(
                result.error_code or "nia_permanent_error"
            )

        if result.response is None or result.http_status is None:
            return ConnectorHandlerResult.failed("nia_success_result_invalid")

        applied = await self._store.save_nia_response(
            event.event_key,
            self._lease_owner,
            build_output_review(event, result.response),
            http_status=result.http_status,
            workflow_guard=guard,
            now=self._clock(),
        )
        if not applied:
            return ConnectorHandlerResult.lease_lost()
        return ConnectorHandlerResult.applied()

    def _pilot_rejection_reason(
        self,
        event: ConnectorEventRecord,
    ) -> Optional[str]:
        try:
            normalized = NormalizedBitrixEvent.model_validate(
                event.normalized_event
            )
            decision = self._pilot_policy_provider().evaluate(normalized)
        except Exception:
            return "pilot_scope_revalidation_invalid"
        return None if decision.accepted else decision.reason

    @staticmethod
    def _approved_payload(
        event: ConnectorEventRecord,
    ) -> Optional[NiaTextPayloadPreview]:
        if event.processing_stage != "nia_dispatch":
            return None
        review = event.preflight_review or {}
        input_decision = event.input_decision or {}
        if input_decision.get("decision") != "approved":
            return None
        if input_decision.get("content_hash") != review.get("content_hash"):
            return None
        payload = review.get("nia_payload_preview")
        if payload is None:
            return None
        try:
            parsed = NiaTextPayloadPreview.model_validate(payload)
        except ValidationError:
            return None
        if build_nia_payload_hash(parsed) != review.get("content_hash"):
            return None
        return parsed
