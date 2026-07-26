"""Adaptador inyectable para ensayar las cuatro decisiones del Review Lab."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from .review_approval import (
    ReviewDecisionAction,
    ReviewDecisionIntent,
    ReviewExpectedStatus,
)
from .review_decision_service import ReviewDecisionServiceResponse


REVIEW_DECISION_PATH = "/bitrix-connector/review"
_ACTION_CONTRACT = {
    ReviewDecisionAction.APPROVE_INPUT: (
        "approve-input",
        ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
        "APROBAR ENVIO A NIA",
    ),
    ReviewDecisionAction.REJECT_INPUT: (
        "reject-input",
        ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
        "RECHAZAR ENTRADA",
    ),
    ReviewDecisionAction.APPROVE_OUTPUT: (
        "approve-output",
        ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
        "APROBAR ENVIO A BITRIX",
    ),
    ReviewDecisionAction.REJECT_OUTPUT: (
        "reject-output",
        ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
        "RECHAZAR SALIDA",
    ),
}


class ReviewLabDecisionAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ReviewLabDecisionAttempt(BaseModel):
    """Intento visible; excluye por diseño Bearer, actor y credenciales."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: ReviewDecisionAction
    intent: ReviewDecisionIntent

    @property
    def path(self) -> str:
        route, _, _ = _ACTION_CONTRACT[self.action]
        return f"{REVIEW_DECISION_PATH}/{self.event_key}/{route}"

    def request_payload(self) -> dict[str, object]:
        return self.intent.model_dump(mode="json", exclude_none=True)


class ReviewLabDecisionResult(BaseModel):
    """Proyección segura y directamente renderizable en el laboratorio."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ReviewDecisionAction
    path: str
    request_payload: dict[str, object]
    status_code: int
    code: str
    visual_state: Literal["applied", "replayed", "conflict", "blocked"]
    request_id: Optional[str] = None
    receipt: Optional[dict[str, object]] = None


class HttpReviewLabDecisionAdapter:
    """POST inyectable; ASGITransport permite usarlo sin sockets ni servidor."""

    def __init__(
        self,
        *,
        base_url: str,
        review_token: str,
        timeout_seconds: float = 10.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        cleaned_url = base_url.strip().rstrip("/")
        parsed = httpx.URL(cleaned_url)
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            raise ValueError("review_lab_decision_base_url_invalid")
        if parsed.userinfo or parsed.query or parsed.fragment:
            raise ValueError("review_lab_decision_base_url_invalid")
        if parsed.path not in {"", "/"}:
            raise ValueError("review_lab_decision_base_url_must_be_root")
        if timeout_seconds <= 0:
            raise ValueError("review_lab_decision_timeout_invalid")
        if not review_token.strip():
            raise ValueError("review_lab_decision_token_required")

        self._base_url = cleaned_url
        self._review_token = SecretStr(review_token.strip())
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    async def decide(
        self,
        attempt: ReviewLabDecisionAttempt,
    ) -> ReviewLabDecisionResult:
        try:
            response = await self._http_client.post(
                f"{self._base_url}{attempt.path}",
                json=attempt.request_payload(),
                headers={
                    "Authorization": (
                        "Bearer " + self._review_token.get_secret_value()
                    ),
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
            )
        except httpx.TimeoutException as exc:
            raise ReviewLabDecisionAdapterError(
                "review_lab_decision_timeout"
            ) from exc
        except httpx.TransportError as exc:
            raise ReviewLabDecisionAdapterError(
                "review_lab_decision_unavailable"
            ) from exc

        try:
            service_response = ReviewDecisionServiceResponse.model_validate(
                response.json()
            )
        except (ValueError, ValidationError) as exc:
            raise ReviewLabDecisionAdapterError(
                "review_lab_decision_invalid_response"
            ) from exc
        if service_response.status_code != response.status_code:
            raise ReviewLabDecisionAdapterError(
                "review_lab_decision_invalid_response"
            )

        return ReviewLabDecisionResult(
            action=attempt.action,
            path=attempt.path,
            request_payload=attempt.request_payload(),
            status_code=service_response.status_code,
            code=service_response.code,
            visual_state=self._visual_state(service_response),
            request_id=service_response.request_id,
            receipt=(
                service_response.receipt.model_dump(mode="json", exclude_none=True)
                if service_response.receipt is not None
                else None
            ),
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "HttpReviewLabDecisionAdapter":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @staticmethod
    def _visual_state(
        response: ReviewDecisionServiceResponse,
    ) -> Literal["applied", "replayed", "conflict", "blocked"]:
        if response.code == "review_applied":
            return "applied"
        if response.code == "review_replayed":
            return "replayed"
        if response.status_code == 409:
            return "conflict"
        return "blocked"


class ReviewLabDecisionController:
    """Construye el contrato exacto y conserva el UUID para replays explícitos."""

    def __init__(
        self,
        adapter: HttpReviewLabDecisionAdapter,
        *,
        decision_id_factory=uuid4,
    ) -> None:
        self._adapter = adapter
        self._decision_id_factory = decision_id_factory

    async def decide(
        self,
        *,
        event_key: str,
        action: ReviewDecisionAction,
        content_hash: str,
        reason: Optional[str] = None,
        decision_id: Optional[UUID] = None,
    ) -> ReviewLabDecisionResult:
        parsed_action = ReviewDecisionAction(action)
        _, expected_status, confirmation = _ACTION_CONTRACT[parsed_action]
        resolved_id = decision_id or self._decision_id_factory()
        attempt = ReviewLabDecisionAttempt(
            event_key=event_key,
            action=parsed_action,
            intent=ReviewDecisionIntent(
                content_hash=content_hash,
                decision_id=resolved_id,
                expected_status=expected_status,
                confirmation=confirmation,
                reason=reason,
            ),
        )
        return await self._adapter.decide(attempt)
