import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI

from bitrix_connector.review_approval import (
    ReviewDecisionAction,
    ReviewDecisionStage,
)
from bitrix_connector.review_decision_composition import (
    compose_review_decision_resources,
)
from bitrix_connector.review_lab_decision_adapter import (
    HttpReviewLabDecisionAdapter,
    ReviewLabDecisionAdapterError,
    ReviewLabDecisionController,
)
from tests.test_bitrix_durable_review_decision_coordinator import (
    AtomicFakeCollection,
    CONTENT_HASH,
    EVENT_KEY,
    event_document,
)
from tests.test_bitrix_review_decision_audit import AuditFakeCollection


TOKEN = "review-token-controlado-123456789"
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")
NOW = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)
REQUEST_IDS = (
    UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
)


def scenario(*, stage=ReviewDecisionStage.INPUT, request_ids=REQUEST_IDS):
    events = AtomicFakeCollection([event_document(stage=stage)])
    audit = AuditFakeCollection()
    identifiers = iter(request_ids)
    resources = compose_review_decision_resources(
        event_collection=events,
        audit_collection=audit,
        review_token=TOKEN,
        actor="controlled-reviewer",
        credential_id="reviewer:controlled:v1",
        allowed_actions=tuple(ReviewDecisionAction),
        clock=lambda: NOW,
        request_id_factory=lambda: next(identifiers),
    )
    app = FastAPI()
    app.include_router(resources.router)
    return app, events, audit


class ReviewLabDecisionAsgiTests(unittest.IsolatedAsyncioTestCase):
    async def controller_for(self, app):
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://decision-lab.test",
        )
        adapter = HttpReviewLabDecisionAdapter(
            base_url="http://decision-lab.test",
            review_token=TOKEN,
            http_client=client,
        )
        return (
            ReviewLabDecisionController(
                adapter,
                decision_id_factory=lambda: DECISION_ID,
            ),
            client,
        )

    async def test_apply_replay_and_conflict_are_visible_and_durable(self):
        app, events, audit = scenario()
        controller, client = await self.controller_for(app)

        applied = await controller.decide(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            content_hash=CONTENT_HASH,
            decision_id=DECISION_ID,
        )
        replayed = await controller.decide(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            content_hash=CONTENT_HASH,
            decision_id=DECISION_ID,
        )
        conflict = await controller.decide(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            content_hash=CONTENT_HASH,
            decision_id=DECISION_ID,
            reason="significado diferente",
        )
        await client.aclose()

        self.assertEqual(
            (applied.status_code, applied.code, applied.visual_state),
            (200, "review_applied", "applied"),
        )
        self.assertEqual(
            (replayed.status_code, replayed.code, replayed.visual_state),
            (200, "review_replayed", "replayed"),
        )
        self.assertTrue(replayed.receipt["idempotent"])
        self.assertEqual(
            (conflict.status_code, conflict.code, conflict.visual_state),
            (409, "review_idempotency_conflict", "conflict"),
        )
        self.assertEqual(
            [applied.request_id, replayed.request_id, conflict.request_id],
            [str(value) for value in REQUEST_IDS],
        )
        self.assertEqual(events.documents[EVENT_KEY]["status"], "ready_for_nia")
        self.assertEqual(len(events.update_calls), 1)
        self.assertEqual(len(audit.documents), 3)
        self.assertNotIn("actor", applied.request_payload)
        self.assertNotIn("authorization", applied.request_payload)

    async def test_adapter_reaches_each_explicit_route_with_exact_contract(self):
        cases = (
            (
                ReviewDecisionAction.APPROVE_INPUT,
                ReviewDecisionStage.INPUT,
                None,
                "approve-input",
                "ready_for_nia",
            ),
            (
                ReviewDecisionAction.REJECT_INPUT,
                ReviewDecisionStage.INPUT,
                "entrada descartada",
                "reject-input",
                "input_rejected",
            ),
            (
                ReviewDecisionAction.APPROVE_OUTPUT,
                ReviewDecisionStage.OUTPUT,
                None,
                "approve-output",
                "ready_for_bitrix",
            ),
            (
                ReviewDecisionAction.REJECT_OUTPUT,
                ReviewDecisionStage.OUTPUT,
                "salida descartada",
                "reject-output",
                "output_rejected",
            ),
        )
        for index, (action, stage, reason, suffix, target) in enumerate(cases, 1):
            with self.subTest(action=action):
                request_id = UUID(
                    f"00000000-0000-4000-8000-{index:012d}"
                )
                app, events, audit = scenario(
                    stage=stage,
                    request_ids=(request_id,),
                )
                controller, client = await self.controller_for(app)

                result = await controller.decide(
                    event_key=EVENT_KEY,
                    action=action,
                    content_hash=CONTENT_HASH,
                    reason=reason,
                    decision_id=DECISION_ID,
                )
                await client.aclose()

                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.code, "review_applied")
                self.assertTrue(result.path.endswith(f"/{suffix}"))
                self.assertEqual(
                    result.request_payload["expected_status"],
                    (
                        "needs_input_review"
                        if stage is ReviewDecisionStage.INPUT
                        else "needs_output_review"
                    ),
                )
                self.assertEqual(events.documents[EVENT_KEY]["status"], target)
                self.assertEqual(len(audit.documents), 1)

    async def test_wrong_token_is_blocked_without_exposing_credentials(self):
        app, events, audit = scenario(request_ids=())
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://decision-lab.test",
        )
        adapter = HttpReviewLabDecisionAdapter(
            base_url="http://decision-lab.test",
            review_token="token-incorrecto-controlado-12345",
            http_client=client,
        )
        controller = ReviewLabDecisionController(adapter)

        result = await controller.decide(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            content_hash=CONTENT_HASH,
            decision_id=DECISION_ID,
        )
        await client.aclose()

        self.assertEqual(
            (result.status_code, result.code, result.visual_state),
            (401, "review_unauthorized", "blocked"),
        )
        self.assertEqual(events.documents[EVENT_KEY]["status"], "needs_input_review")
        self.assertEqual(audit.documents, {})
        self.assertNotIn("incorrecto", repr(result))
        self.assertNotIn(TOKEN, repr(adapter))

    async def test_invalid_remote_response_is_reduced_to_stable_error(self):
        secret_body = "mongodb://usuario:secreto@interno.invalid"
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(503, text=secret_body)
            )
        )
        adapter = HttpReviewLabDecisionAdapter(
            base_url="http://decision-lab.test",
            review_token=TOKEN,
            http_client=client,
        )
        controller = ReviewLabDecisionController(adapter)

        with self.assertRaises(ReviewLabDecisionAdapterError) as captured:
            await controller.decide(
                event_key=EVENT_KEY,
                action=ReviewDecisionAction.APPROVE_INPUT,
                content_hash=CONTENT_HASH,
                decision_id=DECISION_ID,
            )
        await client.aclose()

        self.assertEqual(
            captured.exception.code,
            "review_lab_decision_invalid_response",
        )
        self.assertNotIn(secret_body, str(captured.exception))
        self.assertNotIn(TOKEN, str(captured.exception))


class ReviewLabDecisionDemoTests(unittest.TestCase):
    def test_demo_is_local_interactive_and_matches_validated_asgi_evidence(self):
        html = (
            Path(__file__).parents[1]
            / "bitrix_connector"
            / "review_lab_decision_demo.html"
        ).read_text(encoding="utf-8")

        self.assertIn('data-source="validated-asgi-fixture"', html)
        self.assertIn('data-real-mode="off"', html)
        self.assertIn("EL NAVEGADOR NO EMITE HTTP", html)
        self.assertIn("ASGITransport + dobles", html)
        self.assertIn("review_applied", html)
        self.assertIn("review_replayed", html)
        self.assertIn("review_idempotency_conflict", html)
        self.assertIn(str(DECISION_ID), html)
        self.assertIn(str(REQUEST_IDS[0]), html)
        for suffix in (
            "approve-input",
            "reject-input",
            "approve-output",
            "reject-output",
        ):
            self.assertIn(suffix, html)
        self.assertEqual(html.count('data-scenario="'), 3)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn(TOKEN, html)
        self.assertNotIn("Bearer ", html)
        self.assertIn("ninguna negociación real", html)


if __name__ == "__main__":
    unittest.main()
