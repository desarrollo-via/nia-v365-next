import json
import unittest
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import FastAPI

from bitrix_connector.review_approval import ReviewDecisionAction
from bitrix_connector.review_decision_composition import (
    compose_review_decision_resources,
)
from bitrix_connector.review_decision_http import REVIEW_DECISION_PREFIX
from tests.test_bitrix_durable_review_decision_coordinator import (
    AtomicFakeCollection,
    event_document,
)
from tests.test_bitrix_review_decision_audit import AuditFakeCollection


TOKEN = "review-token-controlado-123456789"
EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
NOW = datetime(2026, 7, 23, 17, 0, tzinfo=timezone.utc)
DECISION_ID = "12345678-1234-4678-9234-567812345678"


def compose(event_collection, audit_collection, *, token=TOKEN, request_id=None):
    return compose_review_decision_resources(
        event_collection=event_collection,
        audit_collection=audit_collection,
        review_token=token,
        actor="hugo",
        credential_id="reviewer:hugo:v1",
        allowed_actions=tuple(ReviewDecisionAction),
        clock=lambda: NOW,
        request_id_factory=(
            (lambda: UUID(request_id))
            if request_id is not None
            else (lambda: UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
        ),
    )


def request_body():
    return {
        "content_hash": CONTENT_HASH,
        "decision_id": DECISION_ID,
        "expected_status": "needs_input_review",
        "confirmation": "APROBAR ENVIO A NIA",
    }


class ReviewDecisionCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def post(self, resources, *, authorization=f"Bearer {TOKEN}", content=None):
        app = FastAPI()
        app.include_router(resources.router)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://composition.test",
        ) as client:
            return await client.post(
                f"{REVIEW_DECISION_PREFIX}/{EVENT_KEY}/approve-input",
                headers={
                    "Authorization": authorization,
                    "Content-Type": "application/json",
                },
                content=content,
            )

    async def test_build_has_no_io_and_index_initialization_is_explicit(self):
        events = AtomicFakeCollection([event_document()])
        audit = AuditFakeCollection()

        resources = compose(events, audit)

        self.assertEqual(events.indexes, [])
        self.assertEqual(audit.indexes, [])
        names = await resources.initialize_indexes()
        self.assertEqual(names.decision, "ux_review_decision_ids")
        self.assertEqual(
            names.audit,
            ("ux_review_audit_request_id", "idx_review_audit_decision_time"),
        )
        self.assertEqual(len(events.indexes), 1)
        self.assertEqual(len(audit.indexes), 2)

    async def test_full_asgi_flow_persists_event_and_separate_audit(self):
        events = AtomicFakeCollection([event_document()])
        audit = AuditFakeCollection()
        resources = compose(events, audit)
        await resources.initialize_indexes()

        response = await self.post(
            resources,
            content=json.dumps(request_body()).encode("utf-8"),
        )

        self.assertEqual((response.status_code, response.json()["code"]), (200, "review_applied"))
        stored_event = events.documents[EVENT_KEY]
        self.assertEqual(stored_event["status"], "ready_for_nia")
        self.assertEqual(stored_event["input_decision"]["decision_id"], DECISION_ID)
        self.assertEqual(stored_event["input_decision"]["credential_id"], "reviewer:hugo:v1")
        self.assertEqual(len(audit.documents), 1)
        stored_audit = next(iter(audit.documents.values()))
        self.assertEqual(stored_audit["service_code"], "review_applied")
        self.assertEqual(stored_audit["decision_id"], DECISION_ID)
        self.assertNotIn("authorization", stored_audit)
        self.assertNotIn("payload", stored_audit)

    async def test_recreated_composition_replays_and_writes_second_audit(self):
        events = AtomicFakeCollection([event_document()])
        audit = AuditFakeCollection()
        first = compose(
            events,
            audit,
            request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
        applied = await self.post(
            first,
            content=json.dumps(request_body()).encode("utf-8"),
        )
        recreated = compose(
            events,
            audit,
            request_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        )

        replayed = await self.post(
            recreated,
            content=json.dumps(request_body()).encode("utf-8"),
        )

        self.assertEqual(applied.json()["code"], "review_applied")
        self.assertEqual(replayed.json()["code"], "review_replayed")
        self.assertTrue(replayed.json()["receipt"]["idempotent"])
        self.assertEqual(len(events.documents[EVENT_KEY]["review_decision_ids"]), 1)
        self.assertEqual(len(audit.documents), 2)

    async def test_bad_auth_with_broken_json_touches_neither_collection(self):
        events = AtomicFakeCollection([event_document()])
        audit = AuditFakeCollection()
        resources = compose(events, audit)

        response = await self.post(
            resources,
            authorization="Bearer incorrecto",
            content=b'{"broken":',
        )

        self.assertEqual((response.status_code, response.json()["code"]), (401, "review_unauthorized"))
        self.assertEqual(events.documents[EVENT_KEY]["status"], "needs_input_review")
        self.assertEqual(audit.documents, {})

    async def test_same_collection_and_invalid_auth_config_fail_closed(self):
        shared = AtomicFakeCollection([event_document()])
        with self.assertRaisesRegex(
            ValueError,
            "review_event_and_audit_collections_must_differ",
        ):
            compose_review_decision_resources(
                event_collection=shared,
                audit_collection=shared,
                review_token=TOKEN,
                actor="hugo",
                credential_id="reviewer:hugo:v1",
                allowed_actions=tuple(ReviewDecisionAction),
            )

        events = AtomicFakeCollection([event_document()])
        audit = AuditFakeCollection()
        resources = compose(events, audit, token=None)
        response = await self.post(
            resources,
            content=json.dumps(request_body()).encode("utf-8"),
        )

        self.assertEqual((response.status_code, response.json()["code"]), (503, "review_auth_unavailable"))
        self.assertEqual(events.documents[EVENT_KEY]["status"], "needs_input_review")
        self.assertEqual(audit.documents, {})


class ReviewDecisionCompositionIsolationTests(unittest.TestCase):
    def test_composition_is_not_imported_by_live_mounts(self):
        for path in (
            "bitrix_connector/review_router.py",
            "bitrix_connector/router.py",
            "main.py",
        ):
            with self.subTest(path=path), open(path, encoding="utf-8") as source_file:
                source = source_file.read()
                self.assertNotIn("review_decision_composition", source)
                self.assertNotIn("compose_review_decision_resources", source)

    def test_composition_reads_no_environment_and_creates_no_clients(self):
        with open(
            "bitrix_connector/review_decision_composition.py",
            encoding="utf-8",
        ) as source_file:
            source = source_file.read().lower()

        for forbidden in (
            "getenv",
            "environ",
            "dotenv",
            "asynciomotorclient",
            "mongoclient(",
            "httpx",
            "requests",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
