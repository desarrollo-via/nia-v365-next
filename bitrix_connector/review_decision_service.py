"""Servicio puro de aplicación de decisiones humanas de revisión.

Encadena autenticación, autorización, validación, enlace, coordinación y
auditoría mediante dependencias inyectadas, sin crear recursos o clientes.
"""

from __future__ import annotations

import re
from typing import Awaitable, Callable, Iterable, Optional, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .review_approval import (
    ReviewDecisionAction,
    ReviewDecisionCommand,
    ReviewDecisionIntent,
    ReviewDecisionStage,
    ReviewDecisionValue,
    ReviewPrincipal,
    bind_review_decision,
)
from .review_auth import (
    ReviewAuthenticationOutcome,
    SingleReviewerAuthenticator,
)
from .review_decision_coordinator import (
    ReviewDecisionOutcome,
    ReviewDecisionResult,
)
from .review_decision_audit import (
    ReviewDecisionAuditAttempt,
    ReviewDecisionAuditSink,
)


_EVENT_KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ACTION_STAGE = {
    ReviewDecisionAction.APPROVE_INPUT: ReviewDecisionStage.INPUT,
    ReviewDecisionAction.REJECT_INPUT: ReviewDecisionStage.INPUT,
    ReviewDecisionAction.APPROVE_OUTPUT: ReviewDecisionStage.OUTPUT,
    ReviewDecisionAction.REJECT_OUTPUT: ReviewDecisionStage.OUTPUT,
}
_ACTION_DECISION = {
    ReviewDecisionAction.APPROVE_INPUT: ReviewDecisionValue.APPROVED,
    ReviewDecisionAction.APPROVE_OUTPUT: ReviewDecisionValue.APPROVED,
    ReviewDecisionAction.REJECT_INPUT: ReviewDecisionValue.REJECTED,
    ReviewDecisionAction.REJECT_OUTPUT: ReviewDecisionValue.REJECTED,
}


class ReviewDecisionCoordinator(Protocol):
    async def decide(
        self,
        command: ReviewDecisionCommand,
    ) -> ReviewDecisionResult: ...


class ReviewDecisionReceipt(BaseModel):
    """Proyección segura que puede mostrarse después de una decisión exitosa."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    event_key: str
    stage: str
    outcome: str
    idempotent: bool
    status_before: Optional[str] = None
    status_after: Optional[str] = None
    content_hash: str
    actor: str
    observed_at: str

    @classmethod
    def from_result(cls, result: ReviewDecisionResult) -> "ReviewDecisionReceipt":
        return cls(
            decision_id=str(result.decision_id),
            event_key=result.event_key,
            stage=result.stage.value,
            outcome=result.outcome.value,
            idempotent=result.idempotent,
            status_before=(
                result.status_before.value if result.status_before is not None else None
            ),
            status_after=(
                result.status_after.value if result.status_after is not None else None
            ),
            content_hash=result.content_hash,
            actor=result.actor,
            observed_at=result.observed_at.isoformat(),
        )


class ReviewDecisionServiceResponse(BaseModel):
    """Respuesta independiente del framework y deliberadamente acotada."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status_code: int
    code: str
    request_id: Optional[str] = None
    receipt: Optional[ReviewDecisionReceipt] = None

    @model_validator(mode="after")
    def receipt_only_on_success(self) -> "ReviewDecisionServiceResponse":
        if (self.status_code == 200) != (self.receipt is not None):
            raise ValueError("review_service_receipt_status_mismatch")
        return self


_COORDINATOR_RESPONSE = {
    ReviewDecisionOutcome.NOT_FOUND: (404, "review_not_found"),
    ReviewDecisionOutcome.IDEMPOTENCY_CONFLICT: (
        409,
        "review_idempotency_conflict",
    ),
    ReviewDecisionOutcome.STALE_HASH: (409, "review_hash_mismatch"),
    ReviewDecisionOutcome.STATUS_MISMATCH: (409, "review_status_mismatch"),
    ReviewDecisionOutcome.ALREADY_DECIDED: (409, "review_already_decided"),
    ReviewDecisionOutcome.ARTIFACT_BLOCKED: (409, "review_artifact_blocked"),
}


class InMemoryReviewDecisionService:
    """Orquesta el contrato objetivo sin abrir recursos por cuenta propia."""

    def __init__(
        self,
        *,
        authenticator: SingleReviewerAuthenticator,
        coordinator: ReviewDecisionCoordinator,
        audit_sink: ReviewDecisionAuditSink,
        allowed_actions: Iterable[ReviewDecisionAction],
        request_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._authenticator = authenticator
        self._coordinator = coordinator
        self._audit_sink = audit_sink
        self._request_id_factory = request_id_factory
        self._allowed_actions = frozenset(
            ReviewDecisionAction(action) for action in allowed_actions
        )

    async def handle(
        self,
        *,
        authorization: str,
        event_key: str,
        action: object,
        payload: object,
    ) -> ReviewDecisionServiceResponse:
        """Procesa un objeto ya disponible conservando el orden del servicio."""

        async def supplied_payload() -> object:
            return payload

        return await self.handle_lazy_payload(
            authorization=authorization,
            event_key=event_key,
            action=action,
            payload_loader=supplied_payload,
        )

    async def handle_lazy_payload(
        self,
        *,
        authorization: str,
        event_key: str,
        action: object,
        payload_loader: Callable[[], Awaitable[object]],
    ) -> ReviewDecisionServiceResponse:
        """Autentica y autoriza antes de invocar el decodificador del cuerpo."""

        authentication = self._authenticator.authenticate(authorization)
        if authentication.outcome is ReviewAuthenticationOutcome.UNAVAILABLE:
            return self._error(503, "review_auth_unavailable")
        if authentication.outcome is not ReviewAuthenticationOutcome.AUTHENTICATED:
            return self._error(401, "review_unauthorized")
        if authentication.principal is None:
            return self._error(503, "review_auth_unavailable")

        try:
            request_id = self._request_id_factory()
            if not isinstance(request_id, UUID) or request_id.version != 4:
                raise ValueError
        except Exception:
            return self._error(503, "review_audit_unavailable")

        parsed_action: Optional[ReviewDecisionAction] = None
        intent: Optional[ReviewDecisionIntent] = None
        command: Optional[ReviewDecisionCommand] = None
        result: Optional[ReviewDecisionResult] = None

        async def audited(
            response: ReviewDecisionServiceResponse,
        ) -> ReviewDecisionServiceResponse:
            return await self._audit_response(
                response=response,
                request_id=request_id,
                principal=authentication.principal,
                event_key=event_key,
                action=parsed_action,
                intent=intent,
                command=command,
                result=result,
            )

        try:
            parsed_action = ReviewDecisionAction(action)
        except (TypeError, ValueError):
            return await audited(self._error(404, "review_not_found"))
        if parsed_action not in self._allowed_actions:
            return await audited(self._error(403, "review_forbidden"))

        try:
            payload = await payload_loader()
        except Exception:
            return await audited(self._error(422, "review_invalid_request"))

        try:
            intent = ReviewDecisionIntent.model_validate(payload)
        except (TypeError, ValidationError, ValueError):
            return await audited(self._error(422, "review_invalid_request"))

        try:
            command = bind_review_decision(
                event_key=event_key,
                action=parsed_action,
                intent=intent,
                principal=authentication.principal,
            )
        except (TypeError, ValidationError, ValueError) as error:
            if str(error) == "review_event_key_invalid":
                return await audited(self._error(404, "review_not_found"))
            return await audited(self._error(422, "review_invalid_request"))

        try:
            result = await self._coordinator.decide(command)
        except Exception:
            return await audited(
                self._error(503, "review_coordinator_unavailable")
            )
        if result.outcome is ReviewDecisionOutcome.APPLIED:
            return await audited(
                ReviewDecisionServiceResponse(
                    status_code=200,
                    code=(
                        "review_replayed" if result.idempotent else "review_applied"
                    ),
                    receipt=ReviewDecisionReceipt.from_result(result),
                )
            )
        mapped = _COORDINATOR_RESPONSE.get(result.outcome)
        if mapped is None:
            return await audited(
                self._error(503, "review_coordinator_unavailable")
            )
        status_code, code = mapped
        return await audited(self._error(status_code, code))

    async def _audit_response(
        self,
        *,
        response: ReviewDecisionServiceResponse,
        request_id: UUID,
        principal: ReviewPrincipal,
        event_key: str,
        action: Optional[ReviewDecisionAction],
        intent: Optional[ReviewDecisionIntent],
        command: Optional[ReviewDecisionCommand],
        result: Optional[ReviewDecisionResult],
    ) -> ReviewDecisionServiceResponse:
        safe_event_key = (
            event_key if _EVENT_KEY_PATTERN.fullmatch(event_key or "") else None
        )
        attempt = ReviewDecisionAuditAttempt(
            request_id=request_id,
            recorded_at=principal.authenticated_at,
            actor=principal.actor,
            credential_id=principal.credential_id,
            event_key=safe_event_key,
            action=action,
            stage=(command.stage if command is not None else _ACTION_STAGE.get(action)),
            decision=(
                command.decision
                if command is not None
                else _ACTION_DECISION.get(action)
            ),
            decision_id=(
                command.decision_id
                if command is not None
                else (intent.decision_id if intent is not None else None)
            ),
            content_hash=(
                command.content_hash
                if command is not None
                else (intent.content_hash if intent is not None else None)
            ),
            reason=(
                command.reason
                if command is not None
                else (intent.reason if intent is not None else None)
            ),
            service_code=response.code,
            status_code=response.status_code,
            coordinator_outcome=(result.outcome if result is not None else None),
            idempotent=(result.idempotent if result is not None else None),
            status_before=(result.status_before if result is not None else None),
            status_after=(result.status_after if result is not None else None),
        )
        try:
            await self._audit_sink.record(attempt)
        except Exception:
            return ReviewDecisionServiceResponse(
                status_code=503,
                code="review_audit_unavailable",
                request_id=str(request_id),
            )
        return response.model_copy(update={"request_id": str(request_id)})

    @staticmethod
    def _error(status_code: int, code: str) -> ReviewDecisionServiceResponse:
        return ReviewDecisionServiceResponse(status_code=status_code, code=code)
