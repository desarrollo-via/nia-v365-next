"""Diseño hermetico del lease pre-evento para Bot Next en Chat Test."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .controlled_chat_participant_adapter import (
    ParticipantSafetyState,
    controlled_participant_safety_ready,
)
from .models import NormalizedBitrixEvent
from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DIALOG_ID,
)


MAX_PRE_EVENT_LEASE_SECONDS = 600


class PreEventLeaseArmEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exact_scope: bool
    linked_verified: bool
    bot_nia_absent: bool
    baseline_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


class PreEventLeaseRollbackEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exact_scope: bool
    restored_verified: bool
    bot_next_absent: bool
    bot_nia_absent: bool
    restored_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


LeaseArmOperation = Callable[[], Awaitable[PreEventLeaseArmEvidence]]
LeaseRollbackOperation = Callable[
    [Optional[str]], Awaitable[PreEventLeaseRollbackEvidence]
]


PreEventLeaseState = Literal[
    "DORMANT",
    "ARMED",
    "AWAITING-EVENT",
    "EVENT-CLAIMED",
    "RESTORED",
    "FAILED-RESTORED",
    "EXPIRED-RESTORED",
    "DISARMED",
    "DISARMED-RESTORED",
    "CLOSED",
    "CLOSED-RESTORED",
    "NO-GO",
    "ROLLBACK-FAILED",
]


@dataclass(frozen=True)
class PreEventLeaseSnapshot:
    phase: Literal["M86-CQ"] = "M86-CQ"
    state: PreEventLeaseState = "DORMANT"
    arm_attempts: int = 0
    event_claims: int = 0
    human_message_authorizations: int = 0
    rollback_attempts: int = 0
    lease_verified: bool = False
    event_claimed: bool = False
    rollback_verified: bool = False
    deadline_bound: bool = False
    human_message_allowed_now: bool = False
    exact_bot_id: Literal[373259] = CONTROLLED_BOT_ID
    exact_chat_id: Literal[78733] = CONTROLLED_CHAT_ID
    exact_dialog_id: Literal["chat78733"] = CONTROLLED_DIALOG_ID
    baseline_retained: Literal[False] = False
    baseline_fingerprint_retained: bool = False
    retry_budget: Literal[0] = 0
    oauth_reads: Literal[0] = 0
    oauth_refresh_calls: Literal[0] = 0
    oauth_persistence_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False


class PreEventParticipantLease:
    """Mantiene una vinculación verificada hasta evento, TTL o cierre."""

    def __init__(
        self,
        *,
        safety: ParticipantSafetyState,
        arm: LeaseArmOperation,
        rollback: LeaseRollbackOperation,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not callable(arm)
            or not callable(rollback)
            or not callable(clock)
        ):
            raise TypeError("pre_event_lease_dependency_invalid")
        self._safety = safety
        self._arm: Optional[LeaseArmOperation] = arm
        self._rollback: Optional[LeaseRollbackOperation] = rollback
        self._clock = clock
        self._lock = asyncio.Lock()
        self._state: PreEventLeaseState = "DORMANT"
        self._deadline: Optional[float] = None
        self._baseline_fingerprint: Optional[str] = None
        self._arm_attempts = 0
        self._event_claims = 0
        self._human_message_authorizations = 0
        self._rollback_attempts = 0
        self._lease_verified = False
        self._rollback_verified = False

    async def arm_after_second_confirmation_once(
        self, *, session_deadline: float
    ) -> PreEventLeaseSnapshot:
        async with self._lock:
            if self._state != "DORMANT" or self._arm is None:
                self._terminal("NO-GO")
                return self._snapshot()
            remaining = session_deadline - self._clock()
            if (
                not controlled_participant_safety_ready(self._safety)
                or remaining <= 0
                or remaining > MAX_PRE_EVENT_LEASE_SECONDS
            ):
                self._terminal("NO-GO")
                return self._snapshot()

            arm, self._arm = self._arm, None
            self._arm_attempts = 1
            evidence: Optional[PreEventLeaseArmEvidence] = None
            try:
                evidence = await arm()
            except Exception:
                pass
            if evidence is not None:
                self._baseline_fingerprint = evidence.baseline_fingerprint
            if not self._arm_evidence_exact(evidence):
                await self._rollback_locked(
                    success_state="FAILED-RESTORED"
                )
                return self._snapshot()

            self._lease_verified = True
            self._deadline = session_deadline
            self._state = "ARMED"
            return self._snapshot()

    async def consume_human_message_authorization_once(
        self,
    ) -> PreEventLeaseSnapshot:
        async with self._lock:
            await self._expire_locked()
            if self._state == "ARMED" and self._human_message_authorizations == 0:
                self._human_message_authorizations = 1
                self._state = "AWAITING-EVENT"
            elif self._state in {"ARMED", "AWAITING-EVENT"}:
                await self._rollback_locked(
                    success_state="FAILED-RESTORED"
                )
            return self._snapshot()

    async def claim_exact_event_once(
        self, event: NormalizedBitrixEvent
    ) -> PreEventLeaseSnapshot:
        async with self._lock:
            await self._expire_locked()
            if self._state != "AWAITING-EVENT" or not self._event_exact(event):
                return self._snapshot()
            self._event_claims = 1
            self._state = "EVENT-CLAIMED"
            return self._snapshot()

    async def release_after_event_once(self) -> PreEventLeaseSnapshot:
        async with self._lock:
            if self._state != "EVENT-CLAIMED":
                if self._state not in self._terminal_states():
                    self._terminal("NO-GO")
                return self._snapshot()
            await self._rollback_locked(success_state="RESTORED")
            return self._snapshot()

    async def expire_if_due(self) -> PreEventLeaseSnapshot:
        async with self._lock:
            await self._expire_locked()
            return self._snapshot()

    async def disarm_once(self) -> PreEventLeaseSnapshot:
        async with self._lock:
            if self._state in {"ARMED", "AWAITING-EVENT", "EVENT-CLAIMED"}:
                await self._rollback_locked(
                    success_state="DISARMED-RESTORED"
                )
            elif self._state == "DORMANT":
                self._terminal("DISARMED")
            return self._snapshot()

    async def close(self) -> PreEventLeaseSnapshot:
        async with self._lock:
            if self._state in {"ARMED", "AWAITING-EVENT", "EVENT-CLAIMED"}:
                await self._rollback_locked(
                    success_state="CLOSED-RESTORED"
                )
            elif self._state == "DORMANT":
                self._terminal("CLOSED")
            return self._snapshot()

    async def snapshot(self) -> PreEventLeaseSnapshot:
        async with self._lock:
            await self._expire_locked()
            return self._snapshot()

    async def _expire_locked(self) -> None:
        if (
            self._state not in {"ARMED", "AWAITING-EVENT", "EVENT-CLAIMED"}
            or self._deadline is None
            or self._clock() < self._deadline
        ):
            return
        await self._rollback_locked(success_state="EXPIRED-RESTORED")

    async def _rollback_locked(
        self, *, success_state: PreEventLeaseState
    ) -> None:
        rollback, self._rollback = self._rollback, None
        if self._rollback_attempts or rollback is None:
            self._terminal("ROLLBACK-FAILED")
            return
        self._rollback_attempts = 1
        evidence: Optional[PreEventLeaseRollbackEvidence] = None
        try:
            evidence = await rollback(self._baseline_fingerprint)
        except Exception:
            pass
        exact = bool(
            evidence is not None
            and self._baseline_fingerprint is not None
            and evidence.exact_scope
            and evidence.restored_verified
            and evidence.bot_next_absent
            and evidence.bot_nia_absent
            and evidence.restored_fingerprint
            == self._baseline_fingerprint
        )
        self._rollback_verified = exact
        self._terminal(success_state if exact else "ROLLBACK-FAILED")

    @staticmethod
    def _arm_evidence_exact(
        evidence: Optional[PreEventLeaseArmEvidence],
    ) -> bool:
        return bool(
            evidence is not None
            and evidence.exact_scope
            and evidence.linked_verified
            and evidence.bot_nia_absent
        )

    @staticmethod
    def _event_exact(event: NormalizedBitrixEvent) -> bool:
        return bool(
            isinstance(event, NormalizedBitrixEvent)
            and event.event == "ONIMBOTV2MESSAGEADD"
            and event.bot_id == CONTROLLED_BOT_ID
            and event.chat_id == CONTROLLED_CHAT_ID
            and event.dialog_id == CONTROLLED_DIALOG_ID
        )

    @staticmethod
    def _terminal_states() -> frozenset[str]:
        return frozenset(
            {
                "RESTORED",
                "FAILED-RESTORED",
                "EXPIRED-RESTORED",
                "DISARMED",
                "DISARMED-RESTORED",
                "CLOSED",
                "CLOSED-RESTORED",
                "NO-GO",
                "ROLLBACK-FAILED",
            }
        )

    def _terminal(self, state: PreEventLeaseState) -> None:
        self._state = state
        self._deadline = None
        self._baseline_fingerprint = None
        self._arm = None
        self._rollback = None

    def _snapshot(self) -> PreEventLeaseSnapshot:
        armed = self._state == "ARMED"
        return PreEventLeaseSnapshot(
            state=self._state,
            arm_attempts=self._arm_attempts,
            event_claims=self._event_claims,
            human_message_authorizations=self._human_message_authorizations,
            rollback_attempts=self._rollback_attempts,
            lease_verified=self._lease_verified,
            event_claimed=self._state == "EVENT-CLAIMED",
            rollback_verified=self._rollback_verified,
            deadline_bound=self._deadline is not None,
            human_message_allowed_now=armed,
            baseline_fingerprint_retained=(
                self._baseline_fingerprint is not None
            ),
        )

    def __repr__(self) -> str:
        return "PreEventParticipantLease(<redacted>)"


__all__ = [
    "MAX_PRE_EVENT_LEASE_SECONDS",
    "PreEventLeaseArmEvidence",
    "PreEventLeaseRollbackEvidence",
    "PreEventLeaseSnapshot",
    "PreEventParticipantLease",
]
