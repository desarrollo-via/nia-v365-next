import asyncio
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from pymongo.errors import DuplicateKeyError

from bitrix_connector.durable_review_decision_coordinator import (
    REVIEW_DECISION_ID_INDEX,
    MongoReviewDecisionCoordinator,
)
from bitrix_connector.review_approval import (
    ReviewDecisionAction,
    ReviewDecisionIntent,
    ReviewDecisionStage,
    ReviewExpectedStatus,
    ReviewPrincipal,
    bind_review_decision,
)
from bitrix_connector.review_auth import SingleReviewerAuthenticator
from bitrix_connector.review_decision_audit import InMemoryReviewDecisionAuditStore
from bitrix_connector.review_decision_coordinator import ReviewDecisionOutcome
from bitrix_connector.review_decision_service import InMemoryReviewDecisionService


EVENT_KEY = "a" * 64
OTHER_EVENT_KEY = "d" * 64
CONTENT_HASH = "b" * 64
NOW = datetime(2026, 7, 23, 14, 0, tzinfo=timezone.utc)
TOKEN = "review-token-controlado-123456789"


class AtomicFakeCollection:
    """Doble mínimo con selector, update e índice único tipo Mongo."""

    def __init__(self, documents=()):
        self.documents = {
            document["event_key"]: deepcopy(document) for document in documents
        }
        self.indexes = []
        self.update_calls = []
        self._lock = asyncio.Lock()

    async def create_index(self, keys, **options):
        self.indexes.append((deepcopy(keys), deepcopy(options)))
        return options["name"]

    @staticmethod
    def _get(document, path):
        value = document
        for part in path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _matches(cls, document, selector):
        for field, expected in selector.items():
            actual = cls._get(document, field)
            if isinstance(expected, dict) and "$ne" in expected:
                forbidden = expected["$ne"]
                if isinstance(actual, list):
                    if forbidden in actual:
                        return False
                elif actual == forbidden:
                    return False
            elif isinstance(actual, list):
                if expected not in actual:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _set(document, path, value):
        target = document
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = deepcopy(value)

    async def find_one(self, selector, projection):
        for document in self.documents.values():
            if self._matches(document, selector):
                return deepcopy(document)
        return None

    async def find_one_and_update(
        self,
        selector,
        update,
        *,
        projection,
        return_document,
    ):
        async with self._lock:
            self.update_calls.append((deepcopy(selector), deepcopy(update)))
            document = next(
                (
                    candidate
                    for candidate in self.documents.values()
                    if self._matches(candidate, selector)
                ),
                None,
            )
            if document is None:
                return None

            for field, value in update.get("$addToSet", {}).items():
                if field == "review_decision_ids":
                    for other in self.documents.values():
                        if other is not document and value in other.get(field, []):
                            raise DuplicateKeyError("duplicate review decision id")
            for field, value in update.get("$set", {}).items():
                self._set(document, field, value)
            for field, value in update.get("$addToSet", {}).items():
                values = document.setdefault(field, [])
                if value not in values:
                    values.append(deepcopy(value))
            return deepcopy(document)


def event_document(
    *,
    event_key=EVENT_KEY,
    stage=ReviewDecisionStage.INPUT,
    status=None,
    content_hash=CONTENT_HASH,
    review_decision="ready_for_review",
):
    if stage is ReviewDecisionStage.INPUT:
        return {
            "event_key": event_key,
            "status": status or "needs_input_review",
            "preflight_review": {
                "content_hash": content_hash,
                "decision": review_decision,
            },
            "input_decision": None,
            "review_decision_ids": [],
        }
    return {
        "event_key": event_key,
        "status": status or "needs_output_review",
        "output_review": {
            "content_hash": content_hash,
            "decision": review_decision,
        },
        "output_decision": None,
        "review_decision_ids": [],
    }


def command(
    *,
    action=ReviewDecisionAction.APPROVE_INPUT,
    event_key=EVENT_KEY,
    identifier=1,
    content_hash=CONTENT_HASH,
    reason=None,
):
    contracts = {
        ReviewDecisionAction.APPROVE_INPUT: (
            ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
            "APROBAR ENVIO A NIA",
        ),
        ReviewDecisionAction.REJECT_INPUT: (
            ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
            "RECHAZAR ENTRADA",
        ),
        ReviewDecisionAction.APPROVE_OUTPUT: (
            ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
            "APROBAR ENVIO A BITRIX",
        ),
        ReviewDecisionAction.REJECT_OUTPUT: (
            ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
            "RECHAZAR SALIDA",
        ),
    }
    expected_status, confirmation = contracts[action]
    if action in (
        ReviewDecisionAction.REJECT_INPUT,
        ReviewDecisionAction.REJECT_OUTPUT,
    ) and reason is None:
        reason = "decisión controlada"
    return bind_review_decision(
        event_key=event_key,
        action=action,
        intent=ReviewDecisionIntent(
            content_hash=content_hash,
            decision_id=UUID(f"12345678-1234-4678-9234-{identifier:012d}"),
            expected_status=expected_status,
            confirmation=confirmation,
            reason=reason,
        ),
        principal=ReviewPrincipal(
            actor="hugo",
            credential_id="reviewer:hugo:v1",
            authenticated_at=NOW,
        ),
    )


class DurableReviewDecisionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_constructor_does_no_io_and_index_is_explicit_unique_sparse(self):
        collection = AtomicFakeCollection([event_document()])
        coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)

        self.assertEqual(collection.indexes, [])
        name = await coordinator.ensure_indexes()

        self.assertEqual(name, REVIEW_DECISION_ID_INDEX)
        _, options = collection.indexes[0]
        self.assertEqual(
            options,
            {"name": REVIEW_DECISION_ID_INDEX, "unique": True, "sparse": True},
        )

    async def test_all_four_actions_are_atomic_and_persist_full_identity(self):
        cases = (
            (ReviewDecisionAction.APPROVE_INPUT, "ready_for_nia", "input_decision"),
            (ReviewDecisionAction.REJECT_INPUT, "input_rejected", "input_decision"),
            (
                ReviewDecisionAction.APPROVE_OUTPUT,
                "ready_for_bitrix",
                "output_decision",
            ),
            (
                ReviewDecisionAction.REJECT_OUTPUT,
                "output_rejected",
                "output_decision",
            ),
        )
        for index, (action, target, decision_field) in enumerate(cases, 1):
            with self.subTest(action=action):
                stage = (
                    ReviewDecisionStage.INPUT
                    if "input" in action.value
                    else ReviewDecisionStage.OUTPUT
                )
                collection = AtomicFakeCollection([event_document(stage=stage)])
                coordinator = MongoReviewDecisionCoordinator(
                    collection,
                    clock=lambda: NOW,
                )

                result = await coordinator.decide(command(action=action, identifier=index))
                stored = collection.documents[EVENT_KEY]

                self.assertEqual(result.outcome, ReviewDecisionOutcome.APPLIED)
                self.assertFalse(result.idempotent)
                self.assertEqual(stored["status"], target)
                self.assertEqual(len(collection.update_calls), 1)
                decision = stored[decision_field]
                self.assertEqual(decision["credential_id"], "reviewer:hugo:v1")
                self.assertEqual(decision["actor"], "hugo")
                self.assertEqual(decision["decided_at"], NOW)
                self.assertRegex(decision["semantic_fingerprint"], r"^[a-f0-9]{64}$")
                self.assertEqual(stored["review_decision_ids"], [decision["decision_id"]])

    async def test_recreated_coordinator_replays_original_decision(self):
        collection = AtomicFakeCollection([event_document()])
        first = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)
        value = command()

        applied = await first.decide(value)
        recreated = MongoReviewDecisionCoordinator(
            collection,
            clock=lambda: datetime(2026, 7, 23, 15, tzinfo=timezone.utc),
        )
        replayed = await recreated.decide(value)

        self.assertFalse(applied.idempotent)
        self.assertTrue(replayed.idempotent)
        self.assertEqual(replayed.observed_at, NOW)
        self.assertEqual(len(collection.update_calls), 1)

    async def test_same_id_with_changed_meaning_is_durable_conflict(self):
        collection = AtomicFakeCollection([event_document()])
        coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)
        await coordinator.decide(command())

        conflict = await coordinator.decide(command(reason="otro significado"))

        self.assertEqual(conflict.outcome, ReviewDecisionOutcome.IDEMPOTENCY_CONFLICT)
        self.assertEqual(collection.documents[EVENT_KEY]["status"], "ready_for_nia")
        self.assertEqual(len(collection.update_calls), 1)

    async def test_concurrent_same_command_applies_once_and_replays_once(self):
        collection = AtomicFakeCollection([event_document()])
        coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)
        value = command()

        results = await asyncio.gather(
            coordinator.decide(value),
            coordinator.decide(value),
        )

        self.assertEqual(
            [result.outcome for result in results],
            [ReviewDecisionOutcome.APPLIED, ReviewDecisionOutcome.APPLIED],
        )
        self.assertEqual(sorted(result.idempotent for result in results), [False, True])
        self.assertEqual(len(collection.documents[EVENT_KEY]["review_decision_ids"]), 1)

    async def test_two_decisions_on_same_artifact_apply_exactly_one(self):
        collection = AtomicFakeCollection([event_document()])
        coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)

        results = await asyncio.gather(
            coordinator.decide(command(identifier=1)),
            coordinator.decide(command(identifier=2)),
        )

        self.assertEqual(
            sorted(result.outcome.value for result in results),
            ["already_decided", "applied"],
        )

    async def test_unique_id_cannot_be_reused_across_events(self):
        collection = AtomicFakeCollection(
            [event_document(), event_document(event_key=OTHER_EVENT_KEY)]
        )
        coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)

        results = await asyncio.gather(
            coordinator.decide(command()),
            coordinator.decide(command(event_key=OTHER_EVENT_KEY)),
        )

        self.assertEqual(
            sorted(result.outcome.value for result in results),
            ["applied", "idempotency_conflict"],
        )
        applied_documents = [
            document
            for document in collection.documents.values()
            if document["status"] == "ready_for_nia"
        ]
        self.assertEqual(len(applied_documents), 1)

    async def test_failed_preconditions_are_distinct_and_do_not_mutate(self):
        cases = (
            (
                [],
                command(),
                ReviewDecisionOutcome.NOT_FOUND,
            ),
            (
                [event_document(status="ready_for_nia")],
                command(),
                ReviewDecisionOutcome.STATUS_MISMATCH,
            ),
            (
                [event_document()],
                command(content_hash="c" * 64),
                ReviewDecisionOutcome.STALE_HASH,
            ),
            (
                [event_document(review_decision="blocked")],
                command(),
                ReviewDecisionOutcome.ARTIFACT_BLOCKED,
            ),
        )
        for documents, value, expected in cases:
            with self.subTest(expected=expected):
                collection = AtomicFakeCollection(documents)
                coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)
                before = deepcopy(collection.documents)

                result = await coordinator.decide(value)

                self.assertEqual(result.outcome, expected)
                self.assertEqual(collection.documents, before)

    async def test_invalid_clock_fails_before_atomic_update(self):
        collection = AtomicFakeCollection([event_document()])
        coordinator = MongoReviewDecisionCoordinator(
            collection,
            clock=lambda: datetime(2026, 7, 23, 14, 0),
        )

        with self.assertRaisesRegex(ValueError, "review_decision_clock_invalid"):
            await coordinator.decide(command())

        self.assertEqual(collection.update_calls, [])
        self.assertEqual(collection.documents[EVENT_KEY]["status"], "needs_input_review")

    async def test_pure_service_accepts_durable_coordinator_without_router(self):
        collection = AtomicFakeCollection([event_document()])
        coordinator = MongoReviewDecisionCoordinator(collection, clock=lambda: NOW)
        service = InMemoryReviewDecisionService(
            authenticator=SingleReviewerAuthenticator(
                review_token=TOKEN,
                actor="hugo",
                credential_id="reviewer:hugo:v1",
                clock=lambda: NOW,
            ),
            coordinator=coordinator,
            audit_sink=InMemoryReviewDecisionAuditStore(),
            allowed_actions=(ReviewDecisionAction.APPROVE_INPUT,),
        )
        body = {
            "content_hash": CONTENT_HASH,
            "decision_id": "12345678-1234-4678-9234-000000000001",
            "expected_status": "needs_input_review",
            "confirmation": "APROBAR ENVIO A NIA",
        }

        applied = await service.handle(
            authorization=f"Bearer {TOKEN}",
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            payload=body,
        )
        replayed = await service.handle(
            authorization=f"Bearer {TOKEN}",
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            payload=body,
        )

        self.assertEqual((applied.status_code, applied.code), (200, "review_applied"))
        self.assertEqual((replayed.status_code, replayed.code), (200, "review_replayed"))


class DurableReviewDecisionIsolationTests(unittest.TestCase):
    def test_module_creates_no_client_and_imports_no_web_or_network_stack(self):
        with open(
            "bitrix_connector/durable_review_decision_coordinator.py",
            encoding="utf-8",
        ) as source_file:
            source = source_file.read().lower()

        for forbidden in (
            "fastapi",
            "httpx",
            "requests",
            "asynciomotorclient",
            "mongoclient(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
