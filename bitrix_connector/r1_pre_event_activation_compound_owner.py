"""One-shot owner that closes protected OAuth before emitting evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from .r1_pre_event_activation_evidence_collector import (
    SanitizedParticipantEvidence,
    SanitizedProtectedSourceEvidence,
)
from .r1_pre_event_activation_preflight import (
    BOT_NEXT_ID,
    BOT_NIA_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DEAL_ID,
    CONTROLLED_DIALOG_ID,
    PROTECTED_SETTING_COUNT,
    PROTECTED_SOURCE_KIND,
    PROTECTED_TARGET_ID,
)


@dataclass(frozen=True)
class SanitizedProtectedParticipantSnapshot:
    host_supports_source: bool
    target_id: str
    record_shape_verified: bool
    setting_count: int
    credential_reads: int
    oauth_reads: int
    refresh_calls: int
    retry_calls: int
    review_auth_configured: bool
    deal_id: int
    chat_id: int
    dialog_id: str
    bot_nia_absent: bool
    bot_next_absent: bool
    participant_reads: int
    participant_pages: int
    secret_values_exposed: bool = False


class ProtectedParticipantSession(Protocol):
    async def collect_once(
        self,
        *,
        target_id: str,
        expected_setting_count: int,
        deal_id: int,
        chat_id: int,
        dialog_id: str,
        bot_ids: tuple[int, int],
    ) -> SanitizedProtectedParticipantSnapshot: ...

    async def close(self) -> None: ...


class ProtectedParticipantSessionFactory(Protocol):
    async def build(self) -> ProtectedParticipantSession: ...


@dataclass(frozen=True)
class CompoundProtectedParticipantEvidence:
    state: Literal["EVIDENCE-COLLECTED", "NO-GO"] = "NO-GO"
    reason: str = "compound_owner_not_run"
    protected: Optional[SanitizedProtectedSourceEvidence] = None
    participants: Optional[SanitizedParticipantEvidence] = None
    session_builds: int = 0
    session_collects: int = 0
    session_closes: int = 0
    resources_closed: bool = False
    activation_authorized: Literal[False] = False
    mutations: Literal[0] = 0


class CompoundProtectedParticipantOwner:
    """Keeps all private resources inside one session and one finally."""

    __slots__ = ("_factory", "_used")

    def __init__(self, *, factory: ProtectedParticipantSessionFactory) -> None:
        if factory is None or not callable(getattr(factory, "build", None)):
            raise TypeError("r1_compound_session_factory_invalid")
        self._factory: Optional[ProtectedParticipantSessionFactory] = factory
        self._used = False

    async def collect_once(self) -> CompoundProtectedParticipantEvidence:
        factory, self._factory = self._factory, None
        if self._used or factory is None:
            self._used = True
            return CompoundProtectedParticipantEvidence(reason="owner_reused")
        self._used = True
        session: Optional[ProtectedParticipantSession] = None
        snapshot: object = None
        builds = 0
        collects = 0
        closes = 0
        close_failed = False
        try:
            session = await factory.build()
            builds = 1
            if (
                session is None
                or not callable(getattr(session, "collect_once", None))
                or not callable(getattr(session, "close", None))
            ):
                raise TypeError("r1_compound_session_invalid")
            collects = 1
            snapshot = await session.collect_once(
                target_id=PROTECTED_TARGET_ID,
                expected_setting_count=PROTECTED_SETTING_COUNT,
                deal_id=CONTROLLED_DEAL_ID,
                chat_id=CONTROLLED_CHAT_ID,
                dialog_id=CONTROLLED_DIALOG_ID,
                bot_ids=(BOT_NIA_ID, BOT_NEXT_ID),
            )
        except Exception:
            snapshot = None
        finally:
            if session is not None and callable(getattr(session, "close", None)):
                try:
                    await session.close()
                    closes = 1
                except BaseException:
                    close_failed = True
        if close_failed:
            return CompoundProtectedParticipantEvidence(
                reason="resource_close_failed",
                session_builds=builds,
                session_collects=collects,
                session_closes=closes,
            )
        if not self._snapshot_exact(snapshot):
            return CompoundProtectedParticipantEvidence(
                reason="compound_evidence_invalid",
                session_builds=builds,
                session_collects=collects,
                session_closes=closes,
                resources_closed=closes == 1,
            )
        return CompoundProtectedParticipantEvidence(
            state="EVIDENCE-COLLECTED",
            reason="exact_closed_compound_evidence",
            protected=SanitizedProtectedSourceEvidence(
                host_supports_protected_source=snapshot.host_supports_source,
                protected_source_kind=PROTECTED_SOURCE_KIND,
                protected_target_id=snapshot.target_id,
                protected_record_shape_verified=snapshot.record_shape_verified,
                protected_setting_count=snapshot.setting_count,
                credential_read_calls=snapshot.credential_reads,
                oauth_read_calls=snapshot.oauth_reads,
                refresh_calls=snapshot.refresh_calls,
                retry_calls=snapshot.retry_calls,
                resources_closed=True,
                review_auth_configured=snapshot.review_auth_configured,
                secret_values_exposed=snapshot.secret_values_exposed,
            ),
            participants=SanitizedParticipantEvidence(
                deal_id=snapshot.deal_id,
                chat_id=snapshot.chat_id,
                dialog_id=snapshot.dialog_id,
                bot_nia_absent=snapshot.bot_nia_absent,
                bot_next_absent=snapshot.bot_next_absent,
            ),
            session_builds=builds,
            session_collects=collects,
            session_closes=closes,
            resources_closed=True,
        )

    @staticmethod
    def _snapshot_exact(snapshot: object) -> bool:
        return bool(
            type(snapshot) is SanitizedProtectedParticipantSnapshot
            and snapshot.host_supports_source
            and snapshot.target_id == PROTECTED_TARGET_ID
            and snapshot.record_shape_verified
            and snapshot.setting_count == PROTECTED_SETTING_COUNT
            and snapshot.credential_reads == 1
            and snapshot.oauth_reads == 1
            and snapshot.refresh_calls == 0
            and snapshot.retry_calls == 0
            and snapshot.review_auth_configured
            and snapshot.deal_id == CONTROLLED_DEAL_ID
            and snapshot.chat_id == CONTROLLED_CHAT_ID
            and snapshot.dialog_id == CONTROLLED_DIALOG_ID
            and snapshot.bot_nia_absent
            and snapshot.bot_next_absent
            and snapshot.participant_reads == 1
            and snapshot.participant_pages == 1
            and not snapshot.secret_values_exposed
        )


class CompoundProtectedParticipantProbePair:
    """Runs the compound owner once, then serves only cached sanitized evidence."""

    __slots__ = ("_cached_participants", "_owner", "_participant_used", "_protected_used")

    def __init__(self, *, owner: CompoundProtectedParticipantOwner) -> None:
        if type(owner) is not CompoundProtectedParticipantOwner:
            raise TypeError("r1_compound_owner_invalid")
        self._owner: Optional[CompoundProtectedParticipantOwner] = owner
        self._cached_participants: Optional[SanitizedParticipantEvidence] = None
        self._protected_used = False
        self._participant_used = False

    async def collect_protected(
        self, *, target_id: str, expected_setting_count: int
    ) -> SanitizedProtectedSourceEvidence:
        owner, self._owner = self._owner, None
        if (
            self._protected_used
            or owner is None
            or target_id != PROTECTED_TARGET_ID
            or expected_setting_count != PROTECTED_SETTING_COUNT
        ):
            self._protected_used = True
            raise RuntimeError("r1_compound_protected_probe_blocked")
        self._protected_used = True
        result = await owner.collect_once()
        if (
            result.state != "EVIDENCE-COLLECTED"
            or result.protected is None
            or result.participants is None
            or not result.resources_closed
        ):
            raise RuntimeError("r1_compound_owner_no_go")
        self._cached_participants = result.participants
        return result.protected

    async def collect_participants(
        self,
        *,
        deal_id: int,
        chat_id: int,
        dialog_id: str,
        bot_ids: tuple[int, int],
    ) -> SanitizedParticipantEvidence:
        participants, self._cached_participants = self._cached_participants, None
        if (
            self._participant_used
            or participants is None
            or deal_id != CONTROLLED_DEAL_ID
            or chat_id != CONTROLLED_CHAT_ID
            or dialog_id != CONTROLLED_DIALOG_ID
            or bot_ids != (BOT_NIA_ID, BOT_NEXT_ID)
        ):
            self._participant_used = True
            raise RuntimeError("r1_compound_participant_probe_blocked")
        self._participant_used = True
        return participants


class CompoundProtectedEvidenceProbe:
    __slots__ = ("_pair",)

    def __init__(self, pair: CompoundProtectedParticipantProbePair) -> None:
        if type(pair) is not CompoundProtectedParticipantProbePair:
            raise TypeError("r1_compound_probe_pair_invalid")
        self._pair = pair

    async def collect(
        self, *, target_id: str, expected_setting_count: int
    ) -> SanitizedProtectedSourceEvidence:
        return await self._pair.collect_protected(
            target_id=target_id,
            expected_setting_count=expected_setting_count,
        )


class CompoundParticipantEvidenceProbe:
    __slots__ = ("_pair",)

    def __init__(self, pair: CompoundProtectedParticipantProbePair) -> None:
        if type(pair) is not CompoundProtectedParticipantProbePair:
            raise TypeError("r1_compound_probe_pair_invalid")
        self._pair = pair

    async def collect(
        self,
        *,
        deal_id: int,
        chat_id: int,
        dialog_id: str,
        bot_ids: tuple[int, int],
    ) -> SanitizedParticipantEvidence:
        return await self._pair.collect_participants(
            deal_id=deal_id,
            chat_id=chat_id,
            dialog_id=dialog_id,
            bot_ids=bot_ids,
        )


def build_compound_evidence_probes(
    *, owner: CompoundProtectedParticipantOwner
) -> tuple[CompoundProtectedEvidenceProbe, CompoundParticipantEvidenceProbe]:
    pair = CompoundProtectedParticipantProbePair(owner=owner)
    return CompoundProtectedEvidenceProbe(pair), CompoundParticipantEvidenceProbe(pair)


__all__ = [
    "CompoundProtectedParticipantEvidence",
    "CompoundProtectedParticipantOwner",
    "CompoundProtectedParticipantProbePair",
    "CompoundProtectedEvidenceProbe",
    "CompoundParticipantEvidenceProbe",
    "ProtectedParticipantSession",
    "ProtectedParticipantSessionFactory",
    "SanitizedProtectedParticipantSnapshot",
    "build_compound_evidence_probes",
]
