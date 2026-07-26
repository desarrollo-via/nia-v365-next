import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from pydantic import ValidationError

from bitrix_connector.review_approval import ReviewDecisionAction
from bitrix_connector.review_auth import SingleReviewerAuthenticator
from bitrix_connector.review_decision_audit import (
    REVIEW_AUDIT_DECISION_TIME_INDEX,
    REVIEW_AUDIT_REQUEST_INDEX,
    InMemoryReviewDecisionAuditStore,
    MongoReviewDecisionAuditStore,
    ReviewDecisionAuditAttempt,
)
from bitrix_connector.review_decision_coordinator import (
    InMemoryReviewDecisionCoordinator,
    ReviewArtifactStatus,
    ReviewDecisionOutcome,
    ReviewDecisionStage,
    ReviewableArtifact,
)
from bitrix_connector.review_decision_service import InMemoryReviewDecisionService


TOKEN = "review-token-controlado-123456789"
EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
NOW = datetime(2026, 7, 23, 15, 0, tzinfo=timezone.utc)
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")


class AuditFakeCollection:
    def __init__(self):
        self.documents = {}
        self.indexes = []

    async def create_index(self, keys, **options):
        self.indexes.append((deepcopy(keys), deepcopy(options)))
        return options["name"]

    async def update_one(self, selector, update, *, upsert):
        request_id = selector["request_id"]
        if request_id in self.documents:
            return SimpleNamespace(upserted_id=None)
        self.documents[request_id] = deepcopy(update["$setOnInsert"])
        return SimpleNamespace(upserted_id=f"audit-{len(self.documents)}")

    async def find_one(self, selector, projection):
        document = self.documents.get(selector["request_id"])
        return deepcopy(document) if document is not None else None


def audit_attempt(**changes):
    values = {
        "request_id": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        "recorded_at": NOW,
        "actor": "hugo",
        "credential_id": "reviewer:hugo:v1",
        "event_key": EVENT_KEY,
        "action": "approve_input",
        "stage": "input",
        "decision": "approved",
        "decision_id": DECISION_ID,
        "content_hash": CONTENT_HASH,
        "reason": "verificado",
        "service_code": "review_applied",
        "status_code": 200,
        "coordinator_outcome": "applied",
        "idempotent": False,
        "status_before": "needs_input_review",
        "status_after": "ready_for_nia",
    }
    values.update(changes)
    return ReviewDecisionAuditAttempt(**values)


def authenticator(token=TOKEN):
    return SingleReviewerAuthenticator(
        review_token=token,
        actor="hugo",
        credential_id="reviewer:hugo:v1",
        clock=lambda: NOW,
    )


def artifact(*, status=ReviewArtifactStatus.NEEDS_INPUT_REVIEW):
    return ReviewableArtifact(
        event_key=EVENT_KEY,
        stage=ReviewDecisionStage.INPUT,
        status=status,
        content_hash=CONTENT_HASH,
    )


def payload(**changes):
    values = {
        "content_hash": CONTENT_HASH,
        "decision_id": str(DECISION_ID),
        "expected_status": "needs_input_review",
        "confirmation": "APROBAR ENVIO A NIA",
    }
    values.update(changes)
    return values


class ReviewDecisionAuditStoreTests(unittest.IsolatedAsyncioTestCase):
    def test_model_rejects_secret_shaped_identity_and_reason(self):
        for changes in (
            {"credential_id": "Bearer secreto"},
            {"reason": "token=valor-secreto"},
            {"actor": "hugo\nadmin"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                audit_attempt(**changes)

    async def test_constructor_has_no_io_and_indexes_are_explicit(self):
        collection = AuditFakeCollection()
        store = MongoReviewDecisionAuditStore(collection)

        self.assertEqual(collection.indexes, [])
        names = await store.ensure_indexes()

        self.assertEqual(
            names,
            (REVIEW_AUDIT_REQUEST_INDEX, REVIEW_AUDIT_DECISION_TIME_INDEX),
        )
        self.assertTrue(collection.indexes[0][1]["unique"])
        self.assertTrue(collection.indexes[1][1]["sparse"])

    async def test_record_is_durable_idempotent_and_allowlisted(self):
        collection = AuditFakeCollection()
        first = MongoReviewDecisionAuditStore(collection)
        attempt = audit_attempt()

        await first.record(attempt)
        recreated = MongoReviewDecisionAuditStore(collection)
        await recreated.record(attempt)
        stored = next(iter(collection.documents.values()))

        self.assertEqual(len(collection.documents), 1)
        self.assertEqual(stored["request_id"], str(attempt.request_id))
        self.assertEqual(stored["decision_id"], str(DECISION_ID))
        self.assertEqual(stored["recorded_at"], NOW)
        self.assertEqual(stored["service_code"], "review_applied")
        self.assertNotIn("authorization", stored)
        self.assertNotIn("payload", stored)
        self.assertNotIn("token", repr(stored).lower())

    async def test_reused_request_id_with_other_record_is_conflict(self):
        collection = AuditFakeCollection()
        store = MongoReviewDecisionAuditStore(collection)
        await store.record(audit_attempt())

        with self.assertRaisesRegex(ValueError, "review_audit_request_id_conflict"):
            await store.record(audit_attempt(service_code="review_replayed"))


class AuditedReviewDecisionServiceTests(unittest.IsolatedAsyncioTestCase):
    def build_service(
        self,
        *,
        audit_store,
        coordinator=None,
        allowed_actions=(ReviewDecisionAction.APPROVE_INPUT,),
        request_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        auth=None,
    ):
        coordinator = coordinator or InMemoryReviewDecisionCoordinator(
            [artifact()],
            clock=lambda: NOW,
        )
        return InMemoryReviewDecisionService(
            authenticator=auth or authenticator(),
            coordinator=coordinator,
            audit_sink=audit_store,
            allowed_actions=allowed_actions,
            request_id_factory=lambda: UUID(request_id),
        )

    async def call(self, service, **changes):
        arguments = {
            "authorization": f"Bearer {TOKEN}",
            "event_key": EVENT_KEY,
            "action": ReviewDecisionAction.APPROVE_INPUT,
            "payload": payload(),
        }
        arguments.update(changes)
        return await service.handle(**arguments)

    async def test_success_and_replay_are_separate_complete_audit_records(self):
        audit_store = InMemoryReviewDecisionAuditStore()
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        first = self.build_service(
            audit_store=audit_store,
            coordinator=coordinator,
            request_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        )
        second = self.build_service(
            audit_store=audit_store,
            coordinator=coordinator,
            request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        )

        applied = await self.call(first)
        replayed = await self.call(second)

        self.assertEqual(applied.code, "review_applied")
        self.assertEqual(replayed.code, "review_replayed")
        self.assertEqual(len(audit_store.attempts), 2)
        attempts = list(audit_store.attempts.values())
        self.assertEqual([item.idempotent for item in attempts], [False, True])
        self.assertEqual(attempts[0].actor, "hugo")
        self.assertEqual(attempts[0].credential_id, "reviewer:hugo:v1")
        self.assertEqual(attempts[0].decision_id, DECISION_ID)
        self.assertEqual(attempts[0].status_before.value, "needs_input_review")
        self.assertEqual(attempts[0].status_after.value, "ready_for_nia")

    async def test_each_authenticated_failure_is_audited_without_raw_input(self):
        cases = (
            ((), payload(), 403, "review_forbidden"),
            (
                (ReviewDecisionAction.APPROVE_INPUT,),
                {"actor": "cliente", "reason": "token=secreto"},
                422,
                "review_invalid_request",
            ),
        )
        for index, (allowed, body, status, code) in enumerate(cases, 1):
            with self.subTest(code=code):
                audit_store = InMemoryReviewDecisionAuditStore()
                service = self.build_service(
                    audit_store=audit_store,
                    allowed_actions=allowed,
                    request_id=f"dddddddd-dddd-4ddd-8ddd-{index:012d}",
                )

                response = await self.call(service, payload=body)
                attempt = next(iter(audit_store.attempts.values()))
                serialized = attempt.model_dump_json()

                self.assertEqual((response.status_code, response.code), (status, code))
                self.assertEqual(attempt.service_code, code)
                self.assertIsNone(attempt.reason)
                self.assertNotIn(TOKEN, serialized)
                self.assertNotIn("cliente", serialized)
                self.assertNotIn("secreto", serialized)

    async def test_invalid_event_key_is_redacted_from_audit(self):
        audit_store = InMemoryReviewDecisionAuditStore()
        service = self.build_service(audit_store=audit_store)

        response = await self.call(service, event_key="token=valor-secreto")
        attempt = next(iter(audit_store.attempts.values()))

        self.assertEqual(response.code, "review_not_found")
        self.assertIsNone(attempt.event_key)
        self.assertNotIn("valor-secreto", attempt.model_dump_json())

    async def test_rejection_conflict_and_coordinator_failure_are_audited(self):
        rejection_audit = InMemoryReviewDecisionAuditStore()
        rejection_service = self.build_service(
            audit_store=rejection_audit,
            allowed_actions=(ReviewDecisionAction.REJECT_INPUT,),
            request_id="11111111-1111-4111-8111-111111111111",
        )
        rejected = await self.call(
            rejection_service,
            action=ReviewDecisionAction.REJECT_INPUT,
            payload=payload(
                confirmation="RECHAZAR ENTRADA",
                reason="fuera de alcance",
            ),
        )

        stale_audit = InMemoryReviewDecisionAuditStore()
        stale_service = self.build_service(
            audit_store=stale_audit,
            request_id="22222222-2222-4222-8222-222222222222",
        )
        stale = await self.call(
            stale_service,
            payload=payload(content_hash="c" * 64),
        )

        class FailingCoordinator:
            async def decide(self, command):
                raise RuntimeError("coordinator-secret")

        failure_audit = InMemoryReviewDecisionAuditStore()
        failure_service = self.build_service(
            audit_store=failure_audit,
            coordinator=FailingCoordinator(),
            request_id="33333333-3333-4333-8333-333333333333",
        )
        failed = await self.call(failure_service)

        rejection_attempt = next(iter(rejection_audit.attempts.values()))
        stale_attempt = next(iter(stale_audit.attempts.values()))
        failure_attempt = next(iter(failure_audit.attempts.values()))
        self.assertEqual(rejected.code, "review_applied")
        self.assertEqual(rejection_attempt.decision.value, "rejected")
        self.assertEqual(rejection_attempt.reason, "fuera de alcance")
        self.assertEqual(stale.code, "review_hash_mismatch")
        self.assertEqual(
            stale_attempt.coordinator_outcome,
            ReviewDecisionOutcome.STALE_HASH,
        )
        self.assertEqual(failed.code, "review_coordinator_unavailable")
        self.assertEqual(failure_attempt.service_code, failed.code)
        self.assertNotIn("coordinator-secret", failure_attempt.model_dump_json())

    async def test_unauthenticated_attempt_is_not_audited(self):
        audit_store = InMemoryReviewDecisionAuditStore()
        service = self.build_service(audit_store=audit_store)

        response = await self.call(service, authorization="Bearer incorrecto")

        self.assertEqual(response.code, "review_unauthorized")
        self.assertEqual(audit_store.attempts, {})

    async def test_audit_failure_returns_503_and_retry_is_idempotently_audited(self):
        class FlakyAuditStore(InMemoryReviewDecisionAuditStore):
            def __init__(self):
                super().__init__()
                self.fail = True

            async def record(self, attempt):
                if self.fail:
                    self.fail = False
                    raise RuntimeError("audit-secret")
                await super().record(attempt)

        audit_store = FlakyAuditStore()
        coordinator = InMemoryReviewDecisionCoordinator([artifact()], clock=lambda: NOW)
        first = self.build_service(
            audit_store=audit_store,
            coordinator=coordinator,
            request_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        )
        second = self.build_service(
            audit_store=audit_store,
            coordinator=coordinator,
            request_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
        )

        unavailable = await self.call(first)
        replayed = await self.call(second)

        self.assertEqual(unavailable.code, "review_audit_unavailable")
        self.assertEqual(unavailable.status_code, 503)
        self.assertNotIn("audit-secret", unavailable.model_dump_json())
        self.assertEqual(replayed.code, "review_replayed")
        self.assertEqual(len(audit_store.attempts), 1)
        self.assertTrue(next(iter(audit_store.attempts.values())).idempotent)


class ReviewDecisionAuditIsolationTests(unittest.TestCase):
    def test_audit_module_creates_no_clients_or_web_dependencies(self):
        with open(
            "bitrix_connector/review_decision_audit.py",
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
