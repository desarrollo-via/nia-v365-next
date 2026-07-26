import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.config import (
    DEFAULT_REVIEW_AUDIT_COLLECTION,
    ConnectorMode,
    load_settings,
)
from bitrix_connector.review_decision_http import (
    REVIEW_DECISION_MOUNT_PREFIX,
    build_review_decision_router,
)
from bitrix_connector.review_decision_runtime import (
    ReviewDecisionRuntime,
    ReviewDecisionRuntimeState,
)
from bitrix_connector.router import router as connector_router
from tests.test_bitrix_durable_review_decision_coordinator import (
    AtomicFakeCollection,
    CONTENT_HASH,
    EVENT_KEY,
    event_document,
)
from tests.test_bitrix_review_decision_audit import AuditFakeCollection


TOKEN = "review-token-controlado-123456789"
DECISION_ID = "12345678-1234-4678-9234-567812345678"


class FakeDatabase:
    def __init__(self, collections):
        self.collections = collections
        self.requested = []

    def __getitem__(self, name):
        self.requested.append(name)
        return self.collections[name]


class FakeMongoClient:
    def __init__(self, database):
        self.database = database
        self.requested = []
        self.close_calls = 0

    def __getitem__(self, name):
        self.requested.append(name)
        return self.database

    def close(self):
        self.close_calls += 1


class FailingAuditCollection(AuditFakeCollection):
    async def create_index(self, keys, **options):
        raise RuntimeError("mongodb://usuario:secreto@interno.invalid")


def enabled_settings(**changes):
    values = {
        "activation_locked": False,
        "effective_mode": ConnectorMode.REVIEW,
        "external_calls_enabled": True,
        "mongo_uri": "mongodb://controlled.invalid/nia",
        "mongo_db": "nia",
        "events_collection": "events",
        "review_audit_collection": "review_audit",
        "review_token": TOKEN,
        "review_actor": "hugo",
        "review_credential_id": "reviewer:hugo:v1",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def payload():
    return {
        "content_hash": CONTENT_HASH,
        "decision_id": DECISION_ID,
        "expected_status": "needs_input_review",
        "confirmation": "APROBAR ENVIO A NIA",
    }


def mounted_app(service):
    app = FastAPI()
    parent = APIRouter(prefix="/bitrix-connector")
    parent.include_router(
        build_review_decision_router(
            service,
            prefix=REVIEW_DECISION_MOUNT_PREFIX,
        )
    )
    app.include_router(parent)
    return app


class ReviewDecisionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, app, *, authorization=f"Bearer {TOKEN}", content=None):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://runtime.test",
        ) as client:
            return await client.post(
                f"/bitrix-connector/review/{EVENT_KEY}/approve-input",
                headers={
                    "Authorization": authorization,
                    "Content-Type": "application/json",
                },
                content=content,
            )

    async def test_real_off_is_inert_without_client_indexes_or_body_decode(self):
        client_calls = []

        def forbidden_client(*args, **kwargs):
            client_calls.append((args, kwargs))
            raise AssertionError("mongo client must not be created")

        runtime = ReviewDecisionRuntime(mongo_client_factory=forbidden_client)
        snapshot = await runtime.start(load_settings({}))
        response = await self.request(
            mounted_app(runtime),
            content=b'{"broken":',
        )

        self.assertEqual(snapshot.state, ReviewDecisionRuntimeState.INERT)
        self.assertEqual(snapshot.failure_code, "review_safety_barrier_active")
        self.assertEqual(client_calls, [])
        self.assertEqual(
            (response.status_code, response.json()["code"]),
            (503, "review_runtime_unavailable"),
        )
        stopped = await runtime.close()
        self.assertEqual(stopped.state, ReviewDecisionRuntimeState.STOPPED)

    async def test_configuration_is_validated_before_creating_motor(self):
        calls = []
        runtime = ReviewDecisionRuntime(
            mongo_client_factory=lambda *args, **kwargs: calls.append(
                (args, kwargs)
            )
        )

        same_collection = await runtime.start(
            enabled_settings(review_audit_collection="events")
        )

        self.assertEqual(same_collection.state, ReviewDecisionRuntimeState.INERT)
        self.assertEqual(same_collection.failure_code, "review_configuration_invalid")
        self.assertEqual(calls, [])

    async def test_ready_runtime_initializes_indexes_serves_target_and_closes(self):
        events = AtomicFakeCollection([event_document()])
        audit = AuditFakeCollection()
        database = FakeDatabase({"events": events, "review_audit": audit})
        client = FakeMongoClient(database)
        factory_calls = []

        def client_factory(uri, **options):
            factory_calls.append((uri, options))
            return client

        runtime = ReviewDecisionRuntime(mongo_client_factory=client_factory)
        snapshot = await runtime.start(enabled_settings())
        response = await self.request(
            mounted_app(runtime),
            content=json.dumps(payload()).encode("utf-8"),
        )

        self.assertEqual(snapshot.state, ReviewDecisionRuntimeState.READY)
        self.assertEqual(
            factory_calls,
            [("mongodb://controlled.invalid/nia", {"connect": False})],
        )
        self.assertEqual(client.requested, ["nia"])
        self.assertEqual(database.requested, ["events", "review_audit"])
        self.assertEqual(len(events.indexes), 1)
        self.assertEqual(len(audit.indexes), 2)
        self.assertEqual(
            (response.status_code, response.json()["code"]),
            (200, "review_applied"),
        )
        self.assertEqual(events.documents[EVENT_KEY]["status"], "ready_for_nia")
        self.assertEqual(len(audit.documents), 1)

        first_close = await runtime.close()
        second_close = await runtime.close()
        self.assertEqual(first_close.state, ReviewDecisionRuntimeState.STOPPED)
        self.assertEqual(second_close.state, ReviewDecisionRuntimeState.STOPPED)
        self.assertEqual(client.close_calls, 1)

    async def test_index_failure_closes_client_and_remains_safe(self):
        events = AtomicFakeCollection([event_document()])
        audit = FailingAuditCollection()
        client = FakeMongoClient(
            FakeDatabase({"events": events, "review_audit": audit})
        )
        runtime = ReviewDecisionRuntime(
            mongo_client_factory=lambda *args, **kwargs: client
        )

        snapshot = await runtime.start(enabled_settings())
        response = await self.request(
            mounted_app(runtime),
            content=json.dumps(payload()).encode("utf-8"),
        )

        self.assertEqual(snapshot.state, ReviewDecisionRuntimeState.INERT)
        self.assertEqual(snapshot.failure_code, "review_resources_unavailable")
        self.assertEqual(client.close_calls, 1)
        self.assertEqual(
            (response.status_code, response.json()["code"]),
            (503, "review_runtime_unavailable"),
        )
        self.assertNotIn("secreto", response.text)
        self.assertNotIn("interno.invalid", response.text)


class ReviewDecisionMountedContractTests(unittest.TestCase):
    def test_live_lifecycle_requested_active_remains_inert_before_body_decode(self):
        app = FastAPI()
        app.include_router(connector_router)
        with patch.dict(
            os.environ,
            {"NIA_BITRIX_MODE": "active"},
            clear=True,
        ):
            with TestClient(app) as client:
                response = client.post(
                    f"/bitrix-connector/review/{EVENT_KEY}/approve-input",
                    headers={
                        "Authorization": f"Bearer {TOKEN}",
                        "Content-Type": "application/json",
                    },
                    content=b'{"broken":',
                )

        self.assertEqual(
            (response.status_code, response.json()["code"]),
            (503, "review_runtime_unavailable"),
        )

    def test_configuration_names_are_safe_and_do_not_unlock_calls(self):
        settings = load_settings(
            {
                "NIA_BITRIX_REVIEW_ACTOR": "  hugo  ",
                "NIA_BITRIX_REVIEW_CREDENTIAL_ID": " reviewer:hugo:v1 ",
                "NIA_BITRIX_REVIEW_AUDIT_COLLECTION": " review_audit ",
            }
        )
        defaults = load_settings({})

        self.assertEqual(settings.review_actor, "hugo")
        self.assertEqual(settings.review_credential_id, "reviewer:hugo:v1")
        self.assertEqual(settings.review_audit_collection, "review_audit")
        self.assertEqual(
            defaults.review_audit_collection,
            DEFAULT_REVIEW_AUDIT_COLLECTION,
        )
        self.assertFalse(settings.external_calls_enabled)
        self.assertTrue(settings.activation_locked)
        self.assertEqual(settings.effective_mode, ConnectorMode.OFF)

    def test_live_router_has_one_target_post_and_preserves_each_legacy_get(self):
        route_methods = [
            (method, route.path, route.endpoint.__module__)
            for route in connector_router.routes
            for method in getattr(route, "methods", ())
        ]
        decision_suffixes = (
            "approve-input",
            "reject-input",
            "approve-output",
            "reject-output",
        )
        for suffix in decision_suffixes:
            path = f"/bitrix-connector/review/{{event_key}}/{suffix}"
            matches = [
                module
                for method, candidate, module in route_methods
                if method == "POST" and candidate == path
            ]
            self.assertEqual(matches, ["bitrix_connector.review_decision_http"])

        for path in (
            "/bitrix-connector/review",
            "/bitrix-connector/review/output",
            "/bitrix-connector/review/output/{event_key}",
            "/bitrix-connector/review/{event_key}",
        ):
            matches = [
                module
                for method, candidate, module in route_methods
                if method == "GET" and candidate == path
            ]
            self.assertEqual(matches, ["bitrix_connector.review_router"])

        self.assertFalse(
            any(
                path.startswith("/bitrix-connector/bitrix-connector/")
                for _, path, _ in route_methods
            )
        )

    def test_main_delegates_connector_mounting_to_the_optional_bridge(self):
        with open("main.py", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertNotIn("app.include_router(bitrix_router)", source)
        self.assertNotIn("from bitrix_connector", source)
        self.assertEqual(source.count("mount_optional_bitrix_connector("), 1)
        self.assertNotIn("review_decision_runtime", source)
        self.assertNotIn("build_review_decision_router", source)


if __name__ == "__main__":
    unittest.main()
