import unittest
from datetime import datetime, timezone
from uuid import UUID

from bitrix_connector.review_approval import ReviewDecisionAction
from bitrix_connector.review_auth import SingleReviewerAuthenticator
from bitrix_connector.review_decision_audit import InMemoryReviewDecisionAuditStore
from bitrix_connector.review_decision_coordinator import (
    InMemoryReviewDecisionCoordinator,
    ReviewArtifactStatus,
    ReviewDecisionStage,
    ReviewableArtifact,
)
from bitrix_connector.review_decision_service import InMemoryReviewDecisionService


TOKEN = "review-token-controlado-123456789"
EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
NOW = datetime(2026, 7, 22, 20, 45, tzinfo=timezone.utc)
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")


def authenticator(*, token=TOKEN):
    return SingleReviewerAuthenticator(
        review_token=token,
        actor="hugo",
        credential_id="reviewer:hugo:v1",
        clock=lambda: NOW,
    )


def artifact(
    *,
    event_key=EVENT_KEY,
    status=ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
    stage=ReviewDecisionStage.INPUT,
    content_hash=CONTENT_HASH,
):
    return ReviewableArtifact(
        event_key=event_key,
        status=status,
        stage=stage,
        content_hash=content_hash,
    )


def payload(**changes):
    value = {
        "content_hash": CONTENT_HASH,
        "decision_id": str(DECISION_ID),
        "expected_status": "needs_input_review",
        "confirmation": "APROBAR ENVIO A NIA",
    }
    value.update(changes)
    return value


def service(
    artifacts,
    *,
    auth=None,
    allowed_actions=(ReviewDecisionAction.APPROVE_INPUT,),
):
    coordinator = InMemoryReviewDecisionCoordinator(artifacts, clock=lambda: NOW)
    value = InMemoryReviewDecisionService(
        authenticator=auth or authenticator(),
        coordinator=coordinator,
        audit_sink=InMemoryReviewDecisionAuditStore(),
        allowed_actions=allowed_actions,
    )
    return value, coordinator


async def handle(value, **changes):
    arguments = {
        "authorization": f"Bearer {TOKEN}",
        "event_key": EVENT_KEY,
        "action": ReviewDecisionAction.APPROVE_INPUT,
        "payload": payload(),
    }
    arguments.update(changes)
    return await value.handle(**arguments)


class ReviewDecisionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_composes_all_four_business_actions(self):
        cases = (
            (
                ReviewDecisionAction.APPROVE_INPUT,
                ReviewDecisionStage.INPUT,
                ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                "needs_input_review",
                "APROBAR ENVIO A NIA",
                None,
                "ready_for_nia",
            ),
            (
                ReviewDecisionAction.REJECT_INPUT,
                ReviewDecisionStage.INPUT,
                ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                "needs_input_review",
                "RECHAZAR ENTRADA",
                "no corresponde",
                "input_rejected",
            ),
            (
                ReviewDecisionAction.APPROVE_OUTPUT,
                ReviewDecisionStage.OUTPUT,
                ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
                "needs_output_review",
                "APROBAR ENVIO A BITRIX",
                None,
                "ready_for_bitrix",
            ),
            (
                ReviewDecisionAction.REJECT_OUTPUT,
                ReviewDecisionStage.OUTPUT,
                ReviewArtifactStatus.NEEDS_OUTPUT_REVIEW,
                "needs_output_review",
                "RECHAZAR SALIDA",
                "requiere corrección",
                "output_rejected",
            ),
        )
        for action, stage, status, expected, confirmation, reason, target in cases:
            with self.subTest(action=action):
                value, _ = service(
                    [artifact(stage=stage, status=status)],
                    allowed_actions=(action,),
                )
                response = await handle(
                    value,
                    action=action,
                    payload=payload(
                        expected_status=expected,
                        confirmation=confirmation,
                        reason=reason,
                    ),
                )

                self.assertEqual((response.status_code, response.code), (200, "review_applied"))
                self.assertEqual(response.receipt.stage, stage.value)
                self.assertEqual(response.receipt.status_after, target)

    async def test_valid_request_applies_then_returns_safe_idempotent_receipt(self):
        value, coordinator = service([artifact()])

        applied = await handle(value)
        repeated = await handle(value)

        self.assertEqual((applied.status_code, applied.code), (200, "review_applied"))
        self.assertFalse(applied.receipt.idempotent)
        self.assertEqual(applied.receipt.actor, "hugo")
        self.assertEqual(applied.receipt.status_after, "ready_for_nia")
        self.assertEqual((repeated.status_code, repeated.code), (200, "review_replayed"))
        self.assertTrue(repeated.receipt.idempotent)
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.READY_FOR_NIA,
        )

    async def test_authentication_precedes_action_body_and_coordinator(self):
        value, coordinator = service([artifact()])

        response = await handle(
            value,
            authorization="Bearer incorrecto",
            action="accion-inexistente",
            payload={"actor": "inyectado"},
        )

        self.assertEqual((response.status_code, response.code), (401, "review_unauthorized"))
        self.assertIsNone(response.receipt)
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
        )

    async def test_unconfigured_authentication_returns_503_before_body(self):
        value, coordinator = service([artifact()], auth=authenticator(token=None))

        response = await handle(value, payload={"unexpected": object()})

        self.assertEqual(
            (response.status_code, response.code),
            (503, "review_auth_unavailable"),
        )
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
        )

    async def test_permission_precedes_body_validation(self):
        value, coordinator = service([artifact()], allowed_actions=())

        response = await handle(value, payload={"actor": "inyectado"})

        self.assertEqual((response.status_code, response.code), (403, "review_forbidden"))
        self.assertEqual(
            coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
            ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
        )

    async def test_invalid_body_and_client_actor_are_safe_422(self):
        for invalid in (
            {},
            payload(actor="cliente-no-confiable"),
            payload(content_hash="no-es-hash"),
            payload(confirmation="frase incorrecta"),
        ):
            with self.subTest(invalid=invalid):
                value, coordinator = service([artifact()])
                response = await handle(value, payload=invalid)

                self.assertEqual(
                    (response.status_code, response.code),
                    (422, "review_invalid_request"),
                )
                self.assertIsNone(response.receipt)
                self.assertEqual(
                    coordinator.get_artifact(EVENT_KEY, ReviewDecisionStage.INPUT).status,
                    ReviewArtifactStatus.NEEDS_INPUT_REVIEW,
                )

    async def test_invalid_or_missing_event_is_indistinguishable_404(self):
        value, _ = service([artifact()])

        invalid = await handle(value, event_key="no-es-clave")
        missing = await handle(value, event_key="c" * 64)

        self.assertEqual((invalid.status_code, invalid.code), (404, "review_not_found"))
        self.assertEqual((missing.status_code, missing.code), (404, "review_not_found"))
        self.assertIsNone(invalid.receipt)
        self.assertIsNone(missing.receipt)

    async def test_coordinator_conflicts_have_stable_safe_codes(self):
        stale_service, _ = service([artifact()])
        stale = await handle(stale_service, payload=payload(content_hash="c" * 64))

        status_service, _ = service(
            [artifact(status=ReviewArtifactStatus.READY_FOR_NIA)]
        )
        wrong_status = await handle(status_service)

        decided_service, _ = service([artifact()])
        await handle(decided_service)
        already_decided = await handle(
            decided_service,
            payload=payload(decision_id="12345678-1234-4678-9234-567812345679"),
        )

        conflict_service, _ = service([artifact()])
        await handle(conflict_service)
        conflict = await handle(
            conflict_service,
            payload=payload(reason="mismo UUID, significado distinto"),
        )

        self.assertEqual((stale.status_code, stale.code), (409, "review_hash_mismatch"))
        self.assertEqual(
            (wrong_status.status_code, wrong_status.code),
            (409, "review_status_mismatch"),
        )
        self.assertEqual(
            (already_decided.status_code, already_decided.code),
            (409, "review_already_decided"),
        )
        self.assertEqual(
            (conflict.status_code, conflict.code),
            (409, "review_idempotency_conflict"),
        )
        for response in (stale, wrong_status, already_decided, conflict):
            self.assertIsNone(response.receipt)

    async def test_unknown_action_is_safe_404(self):
        value, _ = service([artifact()])

        response = await handle(value, action="delete-everything")

        self.assertEqual((response.status_code, response.code), (404, "review_not_found"))

    async def test_error_serialization_never_contains_tokens_or_validation_detail(self):
        value, _ = service([artifact()])

        response = await handle(
            value,
            payload=payload(reason="token=secreto-que-no-debe-salir"),
        )
        serialized = response.model_dump_json()

        self.assertEqual(response.code, "review_invalid_request")
        self.assertNotIn(TOKEN, serialized)
        self.assertNotIn("secreto-que-no-debe-salir", serialized)
        self.assertNotIn("validation", serialized.lower())

    async def test_coordinator_failure_is_reduced_to_safe_503(self):
        class FailingCoordinator:
            async def decide(self, command):
                raise RuntimeError("mongo-internal-secret")

        value = InMemoryReviewDecisionService(
            authenticator=authenticator(),
            coordinator=FailingCoordinator(),
            audit_sink=InMemoryReviewDecisionAuditStore(),
            allowed_actions=(ReviewDecisionAction.APPROVE_INPUT,),
        )

        response = await handle(value)
        serialized = response.model_dump_json()

        self.assertEqual(
            (response.status_code, response.code),
            (503, "review_coordinator_unavailable"),
        )
        self.assertNotIn("mongo-internal-secret", serialized)


class ReviewDecisionServiceIsolationTests(unittest.TestCase):
    def test_service_source_has_no_framework_storage_or_client_imports(self):
        with open(
            "bitrix_connector/review_decision_service.py",
            encoding="utf-8",
        ) as source_file:
            source = source_file.read().lower()

        for forbidden in ("fastapi", "motor", "pymongo", "httpx", "requests"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
