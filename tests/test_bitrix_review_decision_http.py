import unittest
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import FastAPI

from bitrix_connector.review_approval import ReviewDecisionAction, ReviewDecisionStage
from bitrix_connector.review_auth import SingleReviewerAuthenticator
from bitrix_connector.review_decision_audit import InMemoryReviewDecisionAuditStore
from bitrix_connector.review_decision_coordinator import (
    InMemoryReviewDecisionCoordinator,
    ReviewArtifactStatus,
    ReviewableArtifact,
)
from bitrix_connector.review_decision_http import (
    REVIEW_DECISION_PREFIX,
    build_review_decision_router,
)
from bitrix_connector.review_decision_service import InMemoryReviewDecisionService


TOKEN = "review-token-controlado-123456789"
EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
NOW = datetime(2026, 7, 23, 16, 0, tzinfo=timezone.utc)
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")


def build_app(
    *,
    stage=ReviewDecisionStage.INPUT,
    status=ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
    allowed_actions=tuple(ReviewDecisionAction),
    token=TOKEN,
):
    artifact = ReviewableArtifact(
        event_key=EVENT_KEY,
        stage=stage,
        status=status,
        content_hash=CONTENT_HASH,
    )
    coordinator = InMemoryReviewDecisionCoordinator([artifact], clock=lambda: NOW)
    audit_store = InMemoryReviewDecisionAuditStore()
    service = InMemoryReviewDecisionService(
        authenticator=SingleReviewerAuthenticator(
            review_token=token,
            actor="hugo",
            credential_id="reviewer:hugo:v1",
            clock=lambda: NOW,
        ),
        coordinator=coordinator,
        audit_sink=audit_store,
        allowed_actions=allowed_actions,
    )
    app = FastAPI()
    app.include_router(build_review_decision_router(service))
    return app, coordinator, audit_store


def payload(**changes):
    values = {
        "content_hash": CONTENT_HASH,
        "decision_id": str(DECISION_ID),
        "expected_status": "needs_input_review",
        "confirmation": "APROBAR ENVIO A NIA",
    }
    values.update(changes)
    return values


class ReviewDecisionHttpTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, app, method, path, **options):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://review.test",
        ) as client:
            return await client.request(method, path, **options)

    async def test_all_four_post_routes_reach_only_the_injected_service(self):
        cases = (
            (
                "approve-input",
                ReviewDecisionStage.INPUT,
                ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                payload(),
                "ready_for_nia",
            ),
            (
                "reject-input",
                ReviewDecisionStage.INPUT,
                ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                payload(
                    confirmation="RECHAZAR ENTRADA",
                    reason="fuera de alcance",
                ),
                "input_rejected",
            ),
            (
                "approve-output",
                ReviewDecisionStage.OUTPUT,
                ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
                payload(
                    expected_status="needs_output_review",
                    confirmation="APROBAR ENVIO A BITRIX",
                ),
                "ready_for_bitrix",
            ),
            (
                "reject-output",
                ReviewDecisionStage.OUTPUT,
                ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
                payload(
                    expected_status="needs_output_review",
                    confirmation="RECHAZAR SALIDA",
                    reason="requiere corrección",
                ),
                "output_rejected",
            ),
        )
        for path, stage, status, body, target in cases:
            with self.subTest(path=path):
                app, coordinator, audit_store = build_app(stage=stage, status=status)

                response = await self.request(
                    app,
                    "POST",
                    f"{REVIEW_DECISION_PREFIX}/{EVENT_KEY}/{path}",
                    headers={"Authorization": f"Bearer {TOKEN}"},
                    json=body,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["code"], "review_applied")
                self.assertEqual(response.json()["receipt"]["status_after"], target)
                self.assertRegex(response.json()["request_id"], r"^[a-f0-9-]{36}$")
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(len(audit_store.attempts), 1)
                self.assertEqual(
                    coordinator.get_artifact(EVENT_KEY, stage).status.value,
                    target,
                )

    async def test_bad_authentication_precedes_malformed_json_decoding(self):
        app, coordinator, audit_store = build_app()
        path = f"{REVIEW_DECISION_PREFIX}/{EVENT_KEY}/approve-input"

        unauthorized = await self.request(
            app,
            "POST",
            path,
            headers={
                "Authorization": "Bearer incorrecto",
                "Content-Type": "application/json",
            },
            content=b'{"json":',
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.json()["code"], "review_unauthorized")
        self.assertEqual(audit_store.attempts, {})
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
        )

        malformed = await self.request(
            app,
            "POST",
            path,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            content=b'{"json":',
        )

        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(malformed.json()["code"], "review_invalid_request")
        self.assertEqual(len(audit_store.attempts), 1)

    async def test_framework_does_not_prevalidate_body_or_client_actor(self):
        app, _, audit_store = build_app()
        route = f"{REVIEW_DECISION_PREFIX}/{EVENT_KEY}/approve-input"

        response = await self.request(
            app,
            "POST",
            route,
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=payload(actor="cliente-no-confiable"),
        )
        operation = app.openapi()["paths"][route.replace(EVENT_KEY, "{event_key}")][
            "post"
        ]

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "review_invalid_request")
        self.assertNotIn("requestBody", operation)
        self.assertEqual(len(audit_store.attempts), 1)
        serialized_audit = next(iter(audit_store.attempts.values())).model_dump_json()
        self.assertNotIn("cliente-no-confiable", serialized_audit)

    async def test_unconfigured_auth_and_wrong_method_fail_closed(self):
        app, _, audit_store = build_app(token=None)
        path = f"{REVIEW_DECISION_PREFIX}/{EVENT_KEY}/approve-input"

        unavailable = await self.request(
            app,
            "POST",
            path,
            json=payload(),
        )
        wrong_method = await self.request(app, "GET", path)

        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["code"], "review_auth_unavailable")
        self.assertEqual(wrong_method.status_code, 405)
        self.assertEqual(audit_store.attempts, {})


class ReviewDecisionHttpIsolationTests(unittest.TestCase):
    def test_target_router_is_mounted_only_by_connector_router(self):
        with open(
            "bitrix_connector/router.py",
            encoding="utf-8",
        ) as source_file:
            connector_source = source_file.read()
        self.assertIn("build_review_decision_router", connector_source)
        self.assertIn("include_decisions=False", connector_source)
        self.assertIn("REVIEW_DECISION_MOUNT_PREFIX", connector_source)

        for path in ("bitrix_connector/review_router.py", "main.py"):
            with self.subTest(path=path), open(path, encoding="utf-8") as source_file:
                source = source_file.read()
                self.assertNotIn("build_review_decision_router", source)

    def test_router_source_has_no_storage_or_external_client_imports(self):
        with open(
            "bitrix_connector/review_decision_http.py",
            encoding="utf-8",
        ) as source_file:
            source = source_file.read().lower()

        for forbidden in (
            "motor",
            "pymongo",
            "httpx",
            "niaclient",
            "bitrixclient",
            "mongoclient",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
