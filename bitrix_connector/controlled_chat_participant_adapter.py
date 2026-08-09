"""Adaptador hermetico para incorporar Bot Next a Chat Test y restaurar."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DIALOG_ID,
    ORIGINAL_WELCOME_BOT_ID,
)


CONTROLLED_DEAL_ID = 614949
BITRIX_CHAT_USER_ADD_METHOD = "imopenlines.crm.chat.user.add"
BITRIX_CHAT_USER_DELETE_METHOD = "imopenlines.crm.chat.user.delete"


class ParticipantSafetyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effective_mode: str
    activation_locked: bool
    external_calls_enabled: bool
    runtime_state: str
    r0_mounted: bool
    r1_active: bool


class ChatParticipantSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    crm_entity_type: Literal["deal"] = "deal"
    crm_entity_id: int
    chat_id: int
    dialog_id: str
    participant_ids: frozenset[int]


class ChatParticipantPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    CRM_ENTITY_TYPE: Literal["deal"] = "deal"
    CRM_ENTITY: Literal[614949] = CONTROLLED_DEAL_ID
    USER_ID: Literal[373259] = CONTROLLED_BOT_ID
    CHAT_ID: Literal[78733] = CONTROLLED_CHAT_ID


class ChatParticipantMutation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal[
        "imopenlines.crm.chat.user.add",
        "imopenlines.crm.chat.user.delete",
    ]
    payload: ChatParticipantPayload = Field(
        default_factory=ChatParticipantPayload
    )


class ControlledParticipantPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: ChatParticipantSnapshot
    add: ChatParticipantMutation
    rollback: ChatParticipantMutation


class ParticipantAdapterStatus(str, Enum):
    RESTORED = "restored"
    FAILED_RESTORED = "failed_restored"
    BLOCKED = "blocked"
    ROLLBACK_FAILED = "rollback_failed"
    ALREADY_USED = "already_used"


class ParticipantAdapterResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ParticipantAdapterStatus
    reason: str
    preflight_reads: int = Field(default=0, ge=0, le=1)
    add_attempts: int = Field(default=0, ge=0, le=1)
    verification_reads: int = Field(default=0, ge=0, le=1)
    rollback_attempts: int = Field(default=0, ge=0, le=1)
    rollback_reads: int = Field(default=0, ge=0, le=1)
    work_attempts: int = Field(default=0, ge=0, le=1)
    work_completed: bool = False
    add_verified: bool = False
    rollback_verified: bool = False


SnapshotReader = Callable[[], Awaitable[ChatParticipantSnapshot]]
ParticipantMutator = Callable[[ChatParticipantMutation], Awaitable[bool]]
LinkedWork = Callable[[], Awaitable[object]]


def controlled_participant_safety_ready(
    safety: ParticipantSafetyState,
) -> bool:
    return bool(
        safety.effective_mode == "off"
        and safety.activation_locked
        and not safety.external_calls_enabled
        and safety.runtime_state == "inert"
        and not safety.r0_mounted
        and safety.r1_active
    )


def build_controlled_participant_plan(
    *,
    safety: ParticipantSafetyState,
    baseline: ChatParticipantSnapshot,
) -> ControlledParticipantPlan:
    """Valida el preflight y produce dos mutaciones fijas e inversas."""

    if not controlled_participant_safety_ready(safety):
        raise ValueError("controlled_participant_safety_barriers_invalid")
    if (
        baseline.crm_entity_id != CONTROLLED_DEAL_ID
        or baseline.chat_id != CONTROLLED_CHAT_ID
        or baseline.dialog_id != CONTROLLED_DIALOG_ID
    ):
        raise ValueError("controlled_participant_scope_mismatch")
    if ORIGINAL_WELCOME_BOT_ID in baseline.participant_ids:
        raise ValueError("bot_nia_must_remain_absent")
    if CONTROLLED_BOT_ID in baseline.participant_ids:
        raise ValueError("bot_next_already_present")

    return ControlledParticipantPlan(
        baseline=baseline,
        add=ChatParticipantMutation(method=BITRIX_CHAT_USER_ADD_METHOD),
        rollback=ChatParticipantMutation(
            method=BITRIX_CHAT_USER_DELETE_METHOD
        ),
    )


class OneShotControlledParticipantAdapter:
    """Ensaya alta y baja exactas con dependencias totalmente inyectadas."""

    def __init__(
        self,
        *,
        safety: ParticipantSafetyState,
        read_snapshot: SnapshotReader,
        mutate: ParticipantMutator,
    ) -> None:
        self._safety = safety
        self._read_snapshot = read_snapshot
        self._mutate = mutate
        self._used = False

    async def rehearse(
        self,
        *,
        while_linked: Optional[LinkedWork] = None,
    ) -> ParticipantAdapterResult:
        if self._used:
            return ParticipantAdapterResult(
                status=ParticipantAdapterStatus.ALREADY_USED,
                reason="controlled_participant_adapter_already_used",
            )
        self._used = True

        if not controlled_participant_safety_ready(self._safety):
            return ParticipantAdapterResult(
                status=ParticipantAdapterStatus.BLOCKED,
                reason="controlled_participant_safety_barriers_invalid",
            )

        try:
            baseline = await self._read_snapshot()
            plan = build_controlled_participant_plan(
                safety=self._safety,
                baseline=baseline,
            )
        except Exception:
            return ParticipantAdapterResult(
                status=ParticipantAdapterStatus.BLOCKED,
                reason="controlled_participant_preflight_blocked",
                preflight_reads=1,
            )

        add_accepted = False
        add_verified = False
        verification_reads = 0
        try:
            add_accepted = await self._mutate(plan.add)
            if add_accepted:
                verification_reads = 1
                linked = await self._read_snapshot()
                add_verified = self._is_exact_linked(plan.baseline, linked)
        except Exception:
            add_accepted = False

        work_attempts = 0
        work_completed = while_linked is None
        if add_verified and while_linked is not None:
            work_attempts = 1
            try:
                await while_linked()
                work_completed = True
            except Exception:
                work_completed = False

        try:
            await self._mutate(plan.rollback)
        except Exception:
            pass

        rollback_reads = 0
        rollback_verified = False
        try:
            rollback_reads = 1
            restored = await self._read_snapshot()
            rollback_verified = restored == plan.baseline
        except Exception:
            rollback_verified = False

        if not rollback_verified:
            return ParticipantAdapterResult(
                status=ParticipantAdapterStatus.ROLLBACK_FAILED,
                reason="controlled_participant_rollback_not_verified",
                preflight_reads=1,
                add_attempts=1,
                verification_reads=verification_reads,
                rollback_attempts=1,
                rollback_reads=rollback_reads,
                work_attempts=work_attempts,
                work_completed=work_completed,
                add_verified=add_verified,
            )
        if add_verified and work_completed:
            return ParticipantAdapterResult(
                status=ParticipantAdapterStatus.RESTORED,
                reason="controlled_participant_rehearsal_restored",
                preflight_reads=1,
                add_attempts=1,
                verification_reads=verification_reads,
                rollback_attempts=1,
                rollback_reads=rollback_reads,
                work_attempts=work_attempts,
                work_completed=work_completed,
                add_verified=True,
                rollback_verified=True,
            )
        return ParticipantAdapterResult(
            status=ParticipantAdapterStatus.FAILED_RESTORED,
            reason=(
                "controlled_participant_linked_work_failed"
                if add_verified
                else "controlled_participant_add_not_verified"
                if add_accepted
                else "controlled_participant_add_not_accepted"
            ),
            preflight_reads=1,
            add_attempts=1,
            verification_reads=verification_reads,
            rollback_attempts=1,
            rollback_reads=rollback_reads,
            work_attempts=work_attempts,
            work_completed=work_completed,
            add_verified=add_verified,
            rollback_verified=True,
        )

    @staticmethod
    def _is_exact_linked(
        baseline: ChatParticipantSnapshot,
        linked: ChatParticipantSnapshot,
    ) -> bool:
        return (
            linked.crm_entity_type == baseline.crm_entity_type
            and linked.crm_entity_id == baseline.crm_entity_id
            and linked.chat_id == baseline.chat_id
            and linked.dialog_id == baseline.dialog_id
            and linked.participant_ids
            == baseline.participant_ids | {CONTROLLED_BOT_ID}
            and ORIGINAL_WELCOME_BOT_ID not in linked.participant_ids
        )


__all__ = [
    "BITRIX_CHAT_USER_ADD_METHOD",
    "BITRIX_CHAT_USER_DELETE_METHOD",
    "CONTROLLED_DEAL_ID",
    "ChatParticipantMutation",
    "ChatParticipantPayload",
    "ChatParticipantSnapshot",
    "ControlledParticipantPlan",
    "OneShotControlledParticipantAdapter",
    "LinkedWork",
    "ParticipantAdapterResult",
    "ParticipantAdapterStatus",
    "ParticipantSafetyState",
    "build_controlled_participant_plan",
    "controlled_participant_safety_ready",
]
