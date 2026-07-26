"""Router objetivo aislado para decisiones humanas de revisión.

La fábrica no se importa ni se monta desde el router vigente o ``main.py``.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .review_approval import ReviewDecisionAction
from .review_decision_service import ReviewDecisionServiceResponse


REVIEW_DECISION_PREFIX = "/bitrix-connector/review"
REVIEW_DECISION_MOUNT_PREFIX = "/review"


class ReviewDecisionHttpService(Protocol):
    async def handle_lazy_payload(
        self,
        *,
        authorization: str,
        event_key: str,
        action: object,
        payload_loader: Callable[[], Awaitable[object]],
    ) -> ReviewDecisionServiceResponse: ...


def build_review_decision_router(
    service: ReviewDecisionHttpService,
    *,
    prefix: str = REVIEW_DECISION_PREFIX,
) -> APIRouter:
    """Construye cuatro POST explícitos sin crear servicios o recursos."""

    router = APIRouter(prefix=prefix, tags=["bitrix-review-target"])

    async def execute(
        request: Request,
        event_key: str,
        action: ReviewDecisionAction,
    ) -> JSONResponse:
        result = await service.handle_lazy_payload(
            authorization=request.headers.get("authorization", ""),
            event_key=event_key,
            action=action,
            payload_loader=request.json,
        )
        return JSONResponse(
            status_code=result.status_code,
            content=result.model_dump(mode="json", exclude_none=True),
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post("/{event_key}/approve-input")
    async def approve_input(request: Request, event_key: str) -> JSONResponse:
        return await execute(request, event_key, ReviewDecisionAction.APPROVE_INPUT)

    @router.post("/{event_key}/reject-input")
    async def reject_input(request: Request, event_key: str) -> JSONResponse:
        return await execute(request, event_key, ReviewDecisionAction.REJECT_INPUT)

    @router.post("/{event_key}/approve-output")
    async def approve_output(request: Request, event_key: str) -> JSONResponse:
        return await execute(request, event_key, ReviewDecisionAction.APPROVE_OUTPUT)

    @router.post("/{event_key}/reject-output")
    async def reject_output(request: Request, event_key: str) -> JSONResponse:
        return await execute(request, event_key, ReviewDecisionAction.REJECT_OUTPUT)

    return router
