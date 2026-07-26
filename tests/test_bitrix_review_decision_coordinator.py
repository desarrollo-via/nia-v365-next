import asyncio
import unittest
from datetime import datetime, timezone
from uuid import UUID

from bitrix_connector.review_approval import (
    ReviewDecisionAction,
    ReviewDecisionIntent,
    ReviewDecisionStage,
    ReviewExpectedStatus,
    ReviewPrincipal,
    bind_review_decision,
)
from bitrix_connector.review_decision_coordinator import (
    InMemoryReviewDecisionCoordinator,
    ReviewArtifactStatus,
    ReviewDecisionOutcome,
    ReviewableArtifact,
)


EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
NOW = datetime(2026, 7, 22, 18, 30, tzinfo=timezone.utc)


def decision_id(number: int) -> UUID:
    return UUID(f"12345678-1234-4678-9234-{number:012d}")


def artifact(
    *,
    stage=ReviewDecisionStage.INPUT,
    status=ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
    content_hash=CONTENT_HASH,
):
    return ReviewableArtifact(
        event_key=EVENT_KEY,
        stage=stage,
        status=status,
        content_hash=content_hash,
    )


def command(
    *,
    action=ReviewDecisionAction.APPROVE_INPUT,
    expected_status=ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
    confirmation="APROBAR ENVIO A NIA",
    reason=None,
    content_hash=CONTENT_HASH,
    identifier=1,
    event_key=EVENT_KEY,
    actor="hugo",
):
    return bind_review_decision(
        event_key=event_key,
        action=action,
        intent=ReviewDecisionIntent(
            content_hash=content_hash,
            decision_id=decision_id(identifier),
            expected_status=expected_status,
            confirmation=confirmation,
            reason=reason,
        ),
        principal=ReviewPrincipal(
            actor=actor,
            credential_id="reviewer:hugo:v1",
            authenticated_at=NOW,
        ),
    )


class ReviewDecisionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_four_decisions_reach_their_single_target_status(self):
        cases = (
            (
                ReviewDecisionAction.APPROVE_INPUT,
                ReviewDecisionStage.INPUT,
                ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
                "APROBAR ENVIO A NIA",
                None,
                ReviewArtifactStatus.READY_FOR_NIA,
            ),
            (
                ReviewDecisionAction.REJECT_INPUT,
                ReviewDecisionStage.INPUT,
                ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
                "RECHAZAR ENTRADA",
                "no corresponde",
                ReviewArtifactStatus.INPUT_REJECTED,
            ),
            (
                ReviewDecisionAction.APPROVE_OUTPUT,
                ReviewDecisionStage.OUTPUT,
                ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
                ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
                "APROBAR ENVIO A BITRIX",
                None,
                ReviewArtifactStatus.READY_FOR_BITRIX,
            ),
            (
                ReviewDecisionAction.REJECT_OUTPUT,
                ReviewDecisionStage.OUTPUT,
                ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
                ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
                "RECHAZAR SALIDA",
                "requiere corrección",
                ReviewArtifactStatus.OUTPUT_REJECTED,
            ),
        )
        for index, (action, stage, current, expected, phrase, reason, target) in enumerate(cases, 1):
            with self.subTest(action=action):
                coordinator = InMemoryReviewDecisionCoordinator(
                    [artifact(stage=stage, status=current)], clock=lambda: NOW
                )
                result = await coordinator.decide(
                    command(
                        action=action,
                        expected_status=expected,
                        confirmation=phrase,
                        reason=reason,
                        identifier=index,
                    )
                )

                self.assertEqual(result.outcome, ReviewDecisionOutcome.APPLIED)
                self.assertFalse(result.idempotent)
                self.assertEqual(result.status_after, target)
                stored = coordinator.get_artifact(EVENT_KEY, stage)
                self.assertEqual(stored.status, target)
                self.assertEqual(stored.actor, "hugo")
                self.assertEqual(stored.decided_at, NOW)

    async def test_exact_repetition_returns_original_result_as_idempotent(self):
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        value = command()

        first = await coordinator.decide(value)
        repeated = await coordinator.decide(value)

        self.assertEqual(first.outcome, ReviewDecisionOutcome.APPLIED)
        self.assertFalse(first.idempotent)
        self.assertEqual(repeated.outcome, ReviewDecisionOutcome.APPLIED)
        self.assertTrue(repeated.idempotent)
        self.assertEqual(repeated.observed_at, first.observed_at)

    async def test_reused_decision_id_with_other_meaning_is_conflict(self):
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        await coordinator.decide(command())

        conflict = await coordinator.decide(command(actor="otro"))

        self.assertEqual(
            conflict.outcome,
            ReviewDecisionOutcome.IDEMPOTENCY_CONFLICT,
        )
        stored = coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT)
        self.assertEqual(stored.actor, "hugo")
        self.assertEqual(stored.status, ReviewArtifactStatus.READY_FOR_NIA)

    async def test_stale_hash_is_remembered_and_never_transitions(self):
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        stale = command(content_hash="c" * 64)

        first = await coordinator.decide(stale)
        repeated = await coordinator.decide(stale)

        self.assertEqual(first.outcome, ReviewDecisionOutcome.STALE_HASH)
        self.assertFalse(first.idempotent)
        self.assertEqual(repeated.outcome, ReviewDecisionOutcome.STALE_HASH)
        self.assertTrue(repeated.idempotent)
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
        )

    async def test_status_mismatch_precedes_hash_check(self):
        coordinator = InMemoryReviewDecisionCoordinator(
            [artifact(status=ReviewArtifactStatus.READY_FOR_NIA)],
            clock=lambda: NOW,
        )

        result = await coordinator.decide(command(content_hash="c" * 64))

        self.assertEqual(result.outcome, ReviewDecisionOutcome.STATUS_MISMATCH)

    async def test_not_found_and_already_decided_are_distinct(self):
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        missing = await coordinator.decide(command(event_key="d" * 64))
        await coordinator.decide(command(identifier=2))
        decided = await coordinator.decide(command(identifier=3))

        self.assertEqual(missing.outcome, ReviewDecisionOutcome.NOT_FOUND)
        self.assertEqual(decided.outcome, ReviewDecisionOutcome.ALREADY_DECIDED)

    async def test_concurrent_identical_clicks_apply_once_and_replay_once(self):
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        value = command()

        results = await asyncio.gather(
            coordinator.decide(value),
            coordinator.decide(value),
        )

        self.assertEqual(
            [result.outcome for result in results],
            [ReviewDecisionOutcome.APPLIED, ReviewDecisionOutcome.APPLIED],
        )
        self.assertEqual(
            sorted(result.idempotent for result in results),
            [False, True],
        )

    async def test_duplicate_artifact_and_invalid_clock_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "review_artifact_duplicate"):
            InMemoryReviewDecisionCoordinator([artifact(), artifact()])

        coordinator = InMemoryReviewDecisionCoordinator(
            [artifact()], clock=lambda: datetime(2026, 7, 22, 18, 30)
        )
        with self.assertRaisesRegex(ValueError, "review_decision_clock_invalid"):
            await coordinator.decide(command())
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
        )


class ReviewDecisionCoordinatorIsolationTests(unittest.TestCase):
    def test_coordinator_source_has_no_framework_storage_or_client_imports(self):
        with open(
            "bitrix_connector/review_decision_coordinator.py",
            encoding="utf-8",
        ) as source_file:
            source = source_file.read().lower()

        for forbidden in ("fastapi", "motor", "pymongo", "httpx", "requests"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
