"""Owner one-shot y superficie autenticada para la activación efímera R1."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bitrix_event_scoped_r1_gate import EventScopedR1Gate
from .bitrix_event_scoped_r1_pre_event_lease import (
    PreEventLeaseSnapshot,
    PreEventParticipantLease,
)
from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)
from .config import ConnectorSettings
from .models import NormalizedBitrixEvent, WebhookReceipt
from .review_auth import (
    ReviewAuthenticationOutcome,
    SingleReviewerAuthenticator,
)


EVENT_R1_CONTROL_PREFIX = "/internal/r1-event"
EVENT_R1_SESSION_TTL_SECONDS = 600
_TERMINAL_GATE_STATES = frozenset({"VERIFIED", "ROLLED-BACK", "NO-GO"})

EventR1ControlState = Literal[
    "IDLE",
    "AWAITING-SECOND-CONFIRMATION",
    "ATTENTION-REQUIRED",
    "VERIFIED",
    "ROLLED-BACK",
    "NO-GO",
    "EXPIRED",
    "DISARMED",
]


class EventR1ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=160)


class EventR1ControlSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M86-CG"] = "M86-CG"
    state: EventR1ControlState
    consumed: bool
    attention_required_now: bool = False
    human_message_required_now: bool = False
    first_confirmation_calls: int = 0
    second_confirmation_calls: int = 0
    event_calls: int = 0
    preflight_calls: int = 0
    roundtrip_calls: int = 0
    disarm_calls: int = 0
    retry_budget: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    oauth_refresh_calls: Literal[0] = 0
    oauth_persistence_calls: Literal[0] = 0
    pre_event_lease_bound: bool = False
    pre_event_lease_state: Optional[str] = None
    participant_arm_attempts: int = 0
    participant_rollback_attempts: int = 0
    participant_rollback_verified: bool = False
    human_message_authorizations: int = 0


class EventScopedR1SessionOwner:
    """Posee como máximo una compuerta; caduca y nunca permite rearmado."""

    def __init__(
        self,
        gate_factory: Callable[[], EventScopedR1Gate],
        *,
        ttl_seconds: int = EVENT_R1_SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        pre_event_lease_factory: Optional[
            Callable[[], PreEventParticipantLease]
        ] = None,
    ) -> None:
        if (
            not callable(gate_factory)
            or type(ttl_seconds) is not int
            or ttl_seconds < 60
            or ttl_seconds > EVENT_R1_SESSION_TTL_SECONDS
            or not callable(clock)
            or (
                pre_event_lease_factory is not None
                and not callable(pre_event_lease_factory)
            )
        ):
            raise TypeError("event_r1_owner_dependency_invalid")
        self._gate_factory: Optional[Callable[[], EventScopedR1Gate]] = gate_factory
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._pre_event_lease_factory = pre_event_lease_factory
        self._lock = asyncio.Lock()
        self._gate: Optional[EventScopedR1Gate] = None
        self._deadline: Optional[float] = None
        self._state: EventR1ControlState = "IDLE"
        self._consumed = False
        self._disarm_calls = 0
        self._pre_event_lease: Optional[PreEventParticipantLease] = None
        self._lease_snapshot: Optional[PreEventLeaseSnapshot] = None
        self._human_message_prompt_pending = False

    def __repr__(self) -> str:
        return "EventScopedR1SessionOwner(<redacted>)"

    async def _expire_locked(self) -> None:
        if (
            self._gate is None
            or self._deadline is None
            or self._gate.snapshot().state in _TERMINAL_GATE_STATES
            or self._clock() < self._deadline
        ):
            return
        if self._pre_event_lease is not None:
            self._lease_snapshot = await self._pre_event_lease.expire_if_due()
        self._gate.close()
        self._gate = None
        self._deadline = None
        self._pre_event_lease_factory = None
        self._state = (
            "NO-GO"
            if self._lease_snapshot is not None
            and self._lease_snapshot.state == "ROLLBACK-FAILED"
            else "EXPIRED"
        )
        self._human_message_prompt_pending = False

    async def _no_go_locked(self) -> None:
        self._consumed = True
        self._gate_factory = None
        self._pre_event_lease_factory = None
        if self._gate is not None:
            self._gate.close()
        if self._pre_event_lease is not None:
            self._lease_snapshot = await self._pre_event_lease.close()
        self._human_message_prompt_pending = False
        self._state = "NO-GO"

    def _snapshot_locked(self) -> EventR1ControlSnapshot:
        gate_snapshot = self._gate.snapshot() if self._gate is not None else None
        state = self._state
        if gate_snapshot is not None and state not in (
            "EXPIRED",
            "DISARMED",
            "NO-GO",
        ):
            state = gate_snapshot.state
        attention = state == "ATTENTION-REQUIRED"
        lease = self._lease_snapshot
        human_message_required = (
            self._human_message_prompt_pending
            if lease is not None
            else attention
        )
        return EventR1ControlSnapshot(
            state=state,
            consumed=self._consumed,
            attention_required_now=attention,
            human_message_required_now=human_message_required,
            first_confirmation_calls=(
                gate_snapshot.first_confirmation_calls if gate_snapshot else 0
            ),
            second_confirmation_calls=(
                gate_snapshot.second_confirmation_calls if gate_snapshot else 0
            ),
            event_calls=gate_snapshot.event_calls if gate_snapshot else 0,
            preflight_calls=gate_snapshot.preflight_calls if gate_snapshot else 0,
            roundtrip_calls=gate_snapshot.roundtrip_calls if gate_snapshot else 0,
            disarm_calls=self._disarm_calls,
            pre_event_lease_bound=lease is not None,
            pre_event_lease_state=lease.state if lease is not None else None,
            participant_arm_attempts=lease.arm_attempts if lease else 0,
            participant_rollback_attempts=(
                lease.rollback_attempts if lease else 0
            ),
            participant_rollback_verified=(
                lease.rollback_verified if lease else False
            ),
            human_message_authorizations=(
                lease.human_message_authorizations if lease else 0
            ),
        )

    async def snapshot(self) -> EventR1ControlSnapshot:
        async with self._lock:
            await self._expire_locked()
            return self._snapshot_locked()

    async def accept_first_confirmation_once(
        self, confirmation: str
    ) -> EventR1ControlSnapshot:
        async with self._lock:
            await self._expire_locked()
            factory, self._gate_factory = self._gate_factory, None
            if self._consumed or self._state != "IDLE" or factory is None:
                await self._no_go_locked()
                return self._snapshot_locked()
            self._consumed = True
            try:
                gate = factory()
                if not isinstance(gate, EventScopedR1Gate):
                    raise TypeError("event_r1_gate_factory_result_invalid")
                self._gate = gate
                self._deadline = self._clock() + self._ttl_seconds
                result = gate.accept_first_confirmation_once(confirmation)
                self._state = result.state
            except Exception:
                await self._no_go_locked()
            return self._snapshot_locked()

    async def accept_second_confirmation_once(
        self, confirmation: str
    ) -> EventR1ControlSnapshot:
        async with self._lock:
            await self._expire_locked()
            if self._state == "EXPIRED":
                return self._snapshot_locked()
            if self._gate is None:
                await self._no_go_locked()
            else:
                result = self._gate.accept_second_confirmation_once(confirmation)
                self._state = result.state
                if self._state == "ATTENTION-REQUIRED":
                    factory, self._pre_event_lease_factory = (
                        self._pre_event_lease_factory,
                        None,
                    )
                    if factory is not None:
                        try:
                            lease = factory()
                            if not isinstance(lease, PreEventParticipantLease):
                                raise TypeError("pre_event_lease_factory_invalid")
                            if self._deadline is None:
                                raise RuntimeError("event_r1_deadline_missing")
                            self._pre_event_lease = lease
                            self._lease_snapshot = (
                                await lease.arm_after_second_confirmation_once(
                                    session_deadline=self._deadline
                                )
                            )
                            if self._lease_snapshot.state != "ARMED":
                                raise RuntimeError("pre_event_lease_arm_failed")
                            self._lease_snapshot = (
                                await lease.consume_human_message_authorization_once()
                            )
                            if self._lease_snapshot.state != "AWAITING-EVENT":
                                raise RuntimeError(
                                    "pre_event_message_authorization_failed"
                                )
                            self._human_message_prompt_pending = True
                        except Exception:
                            await self._no_go_locked()
                elif self._state == "NO-GO":
                    await self._no_go_locked()
            snapshot = self._snapshot_locked()
            self._human_message_prompt_pending = False
            return snapshot

    async def disarm_once(self) -> EventR1ControlSnapshot:
        async with self._lock:
            await self._expire_locked()
            self._disarm_calls += 1
            if self._state == "DISARMED" or self._disarm_calls != 1:
                await self._no_go_locked()
                return self._snapshot_locked()
            self._consumed = True
            self._gate_factory = None
            self._pre_event_lease_factory = None
            if self._gate is not None:
                self._gate.close()
            if self._pre_event_lease is not None:
                self._lease_snapshot = await self._pre_event_lease.disarm_once()
                if self._lease_snapshot.state == "ROLLBACK-FAILED":
                    self._state = "NO-GO"
                    return self._snapshot_locked()
            self._gate = None
            self._deadline = None
            self._state = "DISARMED"
            return self._snapshot_locked()

    async def observe(
        self,
        event: NormalizedBitrixEvent,
        receipt: WebhookReceipt,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
    ) -> None:
        async with self._lock:
            await self._expire_locked()
            gate = self._gate
            if gate is None or self._state != "ATTENTION-REQUIRED":
                return
            lease_claimed = False
            if self._pre_event_lease is not None:
                self._lease_snapshot = (
                    await self._pre_event_lease.claim_exact_event_once(event)
                )
                lease_claimed = self._lease_snapshot.state == "EVENT-CLAIMED"
                if not lease_claimed:
                    return
            try:
                await gate.observe(event, receipt, settings, token_view)
                self._state = gate.snapshot().state
            finally:
                if lease_claimed and self._pre_event_lease is not None:
                    self._lease_snapshot = (
                        await self._pre_event_lease.release_after_event_once()
                    )
                    if self._lease_snapshot.state != "RESTORED":
                        self._state = "NO-GO"
            if self._state in _TERMINAL_GATE_STATES:
                gate.close()


def build_event_r1_control_router(
    owner: EventScopedR1SessionOwner,
    authenticator: SingleReviewerAuthenticator,
    *,
    prefix: str = EVENT_R1_CONTROL_PREFIX,
) -> APIRouter:
    """Expone sólo transiciones categóricas autenticadas y sin caché."""

    router = APIRouter(prefix=prefix, tags=["bitrix-r1-event-control"])

    def response(snapshot: EventR1ControlSnapshot, status_code: int = 200) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=snapshot.model_dump(mode="json"),
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def authenticate(request: Request) -> Optional[JSONResponse]:
        result = authenticator.authenticate(
            request.headers.get("authorization", "")
        )
        if result.accepted:
            return None
        unavailable = result.outcome is ReviewAuthenticationOutcome.UNAVAILABLE
        return JSONResponse(
            status_code=503 if unavailable else 401,
            content={"code": result.reason},
            headers={"Cache-Control": "no-store"},
        )

    async def payload(request: Request, model):
        try:
            return model.model_validate(await request.json())
        except (TypeError, ValueError, ValidationError):
            return None

    def transition_status(snapshot: EventR1ControlSnapshot, expected: str) -> int:
        if snapshot.state == expected:
            return 200
        if snapshot.state == "EXPIRED":
            return 410
        return 409

    @router.get("/status")
    async def status(request: Request) -> JSONResponse:
        rejected = authenticate(request)
        return rejected or response(await owner.snapshot())

    @router.post("/first-confirmation")
    async def first_confirmation(request: Request) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        body = await payload(request, EventR1ConfirmationRequest)
        if body is None:
            return JSONResponse(
                status_code=422,
                content={"code": "event_r1_payload_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        result = await owner.accept_first_confirmation_once(body.confirmation)
        body = None
        return response(result, transition_status(result, "AWAITING-SECOND-CONFIRMATION"))

    @router.post("/second-confirmation")
    async def second_confirmation(request: Request) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        body = await payload(request, EventR1ConfirmationRequest)
        if body is None:
            return JSONResponse(
                status_code=422,
                content={"code": "event_r1_payload_invalid"},
                headers={"Cache-Control": "no-store"},
            )
        result = await owner.accept_second_confirmation_once(body.confirmation)
        body = None
        return response(result, transition_status(result, "ATTENTION-REQUIRED"))

    @router.delete("/session")
    async def disarm(request: Request) -> JSONResponse:
        rejected = authenticate(request)
        if rejected is not None:
            return rejected
        result = await owner.disarm_once()
        return response(result, transition_status(result, "DISARMED"))

    return router


__all__ = [
    "EVENT_R1_CONTROL_PREFIX",
    "EVENT_R1_SESSION_TTL_SECONDS",
    "EventR1ConfirmationRequest",
    "EventR1ControlSnapshot",
    "EventScopedR1SessionOwner",
    "build_event_r1_control_router",
]
