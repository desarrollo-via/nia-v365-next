"""Fábrica hermética de operaciones HTTP para el lease pre-evento R1."""

from __future__ import annotations

import time
from collections.abc import Callable
from hashlib import sha256
from typing import Optional

from .bitrix_event_scoped_r1_pre_event_lease import (
    PreEventLeaseArmEvidence,
    PreEventLeaseRollbackEvidence,
    PreEventParticipantLease,
)
from .controlled_chat_participant_adapter import (
    ChatParticipantMutation,
    ChatParticipantSnapshot,
    ParticipantSafetyState,
    build_controlled_participant_plan,
    controlled_participant_safety_ready,
)
from .controlled_chat_participant_http import (
    ControlledParticipantHttpResources,
    InjectedParticipantOAuthResources,
    ParticipantHttpDecision,
)
from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    ORIGINAL_WELCOME_BOT_ID,
)


FAILED_FINGERPRINT = "0" * 64


def participant_snapshot_fingerprint(
    snapshot: ChatParticipantSnapshot,
) -> str:
    participants = ",".join(
        str(item) for item in sorted(snapshot.participant_ids)
    )
    payload = "|".join(
        (
            snapshot.crm_entity_type,
            str(snapshot.crm_entity_id),
            str(snapshot.chat_id),
            snapshot.dialog_id,
            participants,
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


class InjectedPreEventLeaseOperations:
    """Posee token y HTTP desde arm hasta un único rollback obligatorio."""

    def __init__(
        self,
        *,
        safety: ParticipantSafetyState,
        oauth_resources: InjectedParticipantOAuthResources,
        timeout_seconds: float,
        http_resources_factory=ControlledParticipantHttpResources.build,
    ) -> None:
        if (
            timeout_seconds <= 0
            or not callable(http_resources_factory)
            or oauth_resources is None
        ):
            raise TypeError("pre_event_lease_operations_dependency_invalid")
        self._safety = safety
        self._oauth_resources: Optional[InjectedParticipantOAuthResources] = (
            oauth_resources
        )
        self._timeout_seconds = timeout_seconds
        self._http_resources_factory = http_resources_factory
        self._resources: Optional[ControlledParticipantHttpResources] = None
        self._baseline: Optional[ChatParticipantSnapshot] = None
        self._baseline_fingerprint: Optional[str] = None
        self._arm_used = False
        self._rollback_used = False
        self._add_attempted = False

    async def arm(self) -> PreEventLeaseArmEvidence:
        if self._arm_used or not controlled_participant_safety_ready(self._safety):
            raise RuntimeError("pre_event_lease_arm_unavailable")
        self._arm_used = True
        oauth = self._oauth_resources
        if oauth is None:
            raise RuntimeError("pre_event_lease_oauth_unavailable")
        token = await oauth.oauth_provider.get_access_token(oauth.member_id)
        self._resources = self._http_resources_factory(
            portal_url=oauth.portal_url,
            access_token=token,
            timeout_seconds=self._timeout_seconds,
        )
        token = ""
        read = await self._resources.reader.read()
        if (
            read.decision is not ParticipantHttpDecision.SUCCESS
            or read.snapshot is None
        ):
            raise RuntimeError(
                read.error_code or "pre_event_lease_baseline_unavailable"
            )
        self._baseline = read.snapshot
        self._baseline_fingerprint = participant_snapshot_fingerprint(
            self._baseline
        )

        exact_scope = True
        plan = None
        try:
            plan = build_controlled_participant_plan(
                safety=self._safety,
                baseline=self._baseline,
            )
        except ValueError:
            exact_scope = False

        linked_verified = False
        if plan is not None:
            self._add_attempted = True
            added = await self._resources.mutator.mutate(plan.add)
            if added.decision is ParticipantHttpDecision.SUCCESS:
                linked = await self._resources.reader.read()
                if (
                    linked.decision is ParticipantHttpDecision.SUCCESS
                    and linked.snapshot is not None
                ):
                    linked_verified = self._linked_exact(
                        self._baseline, linked.snapshot
                    )

        return PreEventLeaseArmEvidence(
            exact_scope=exact_scope,
            linked_verified=linked_verified,
            bot_nia_absent=(
                ORIGINAL_WELCOME_BOT_ID not in self._baseline.participant_ids
            ),
            baseline_fingerprint=self._baseline_fingerprint,
        )

    async def rollback(
        self, expected_fingerprint: Optional[str]
    ) -> PreEventLeaseRollbackEvidence:
        if self._rollback_used:
            raise RuntimeError("pre_event_lease_rollback_reused")
        self._rollback_used = True
        baseline = self._baseline
        baseline_fingerprint = self._baseline_fingerprint
        final: Optional[ChatParticipantSnapshot] = None
        resources = self._resources
        try:
            if resources is not None:
                if self._add_attempted:
                    plan = build_controlled_participant_plan(
                        safety=self._safety,
                        baseline=baseline,
                    )
                    await resources.mutator.mutate(plan.rollback)
                read = await resources.reader.read()
                if (
                    read.decision is ParticipantHttpDecision.SUCCESS
                    and read.snapshot is not None
                ):
                    final = read.snapshot
        except Exception:
            final = None
        finally:
            await self._close()

        fingerprint = (
            participant_snapshot_fingerprint(final)
            if final is not None
            else FAILED_FINGERPRINT
        )
        exact_scope = bool(
            final is not None
            and baseline is not None
            and final.crm_entity_type == baseline.crm_entity_type
            and final.crm_entity_id == baseline.crm_entity_id
            and final.chat_id == baseline.chat_id
            and final.dialog_id == baseline.dialog_id
        )
        restored = bool(
            exact_scope
            and expected_fingerprint is not None
            and expected_fingerprint == baseline_fingerprint
            and fingerprint == expected_fingerprint
        )
        return PreEventLeaseRollbackEvidence(
            exact_scope=exact_scope,
            restored_verified=restored,
            bot_next_absent=(
                final is not None
                and CONTROLLED_BOT_ID not in final.participant_ids
            ),
            bot_nia_absent=(
                final is not None
                and ORIGINAL_WELCOME_BOT_ID not in final.participant_ids
            ),
            restored_fingerprint=fingerprint,
        )

    async def _close(self) -> None:
        resources, self._resources = self._resources, None
        oauth, self._oauth_resources = self._oauth_resources, None
        first_error: Optional[BaseException] = None
        if resources is not None:
            try:
                await resources.close()
            except BaseException as exc:
                first_error = exc
        if oauth is not None:
            try:
                await oauth.close()
            except BaseException as exc:
                first_error = first_error or exc
        self._http_resources_factory = lambda **_kwargs: None
        self._baseline = None
        self._baseline_fingerprint = None
        if first_error is not None:
            raise first_error

    @staticmethod
    def _linked_exact(
        baseline: ChatParticipantSnapshot,
        linked: ChatParticipantSnapshot,
    ) -> bool:
        return bool(
            linked.crm_entity_type == baseline.crm_entity_type
            and linked.crm_entity_id == baseline.crm_entity_id
            and linked.chat_id == baseline.chat_id
            and linked.dialog_id == baseline.dialog_id
            and linked.participant_ids
            == baseline.participant_ids | {CONTROLLED_BOT_ID}
            and ORIGINAL_WELCOME_BOT_ID not in linked.participant_ids
        )

    def __repr__(self) -> str:
        return "InjectedPreEventLeaseOperations(<redacted>)"


class InjectedPreEventParticipantLeaseFactory:
    """Crea una sola lease desde recursos OAuth completamente inyectados."""

    def __init__(
        self,
        *,
        safety: ParticipantSafetyState,
        oauth_resources_factory: Callable[
            [], InjectedParticipantOAuthResources
        ],
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        http_resources_factory=ControlledParticipantHttpResources.build,
    ) -> None:
        if (
            not callable(oauth_resources_factory)
            or not callable(clock)
            or not callable(http_resources_factory)
            or timeout_seconds <= 0
        ):
            raise TypeError("pre_event_lease_factory_dependency_invalid")
        self._safety = safety
        self._oauth_resources_factory = oauth_resources_factory
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._http_resources_factory = http_resources_factory
        self._used = False

    def __call__(self) -> PreEventParticipantLease:
        if self._used:
            raise RuntimeError("pre_event_lease_factory_reused")
        self._used = True
        oauth_factory, self._oauth_resources_factory = (
            self._oauth_resources_factory,
            lambda: None,
        )
        operations = InjectedPreEventLeaseOperations(
            safety=self._safety,
            oauth_resources=oauth_factory(),
            timeout_seconds=self._timeout_seconds,
            http_resources_factory=self._http_resources_factory,
        )
        self._http_resources_factory = lambda **_kwargs: None
        return PreEventParticipantLease(
            safety=self._safety,
            arm=operations.arm,
            rollback=operations.rollback,
            clock=self._clock,
        )

    def __repr__(self) -> str:
        return "InjectedPreEventParticipantLeaseFactory(<redacted>)"


__all__ = [
    "InjectedPreEventLeaseOperations",
    "InjectedPreEventParticipantLeaseFactory",
    "participant_snapshot_fingerprint",
]
