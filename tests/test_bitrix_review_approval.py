import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import ValidationError

from bitrix_connector.review_approval import (
    ReviewDecisionAction,
    ReviewDecisionIntent,
    ReviewDecisionStage,
    ReviewDecisionValue,
    ReviewExpectedStatus,
    ReviewPrincipal,
    bind_review_decision,
)


EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")


def principal(**changes):
    values = {
        "actor": "hugo",
        "credential_id": "reviewer:hugo:v1",
        "authenticated_at": datetime(
            2026,
            7,
            22,
            12,
            0,
            tzinfo=timezone(timedelta(hours=-5)),
        ),
    }
    values.update(changes)
    return ReviewPrincipal(**values)


def intent(**changes):
    values = {
        "content_hash": CONTENT_HASH,
        "decision_id": DECISION_ID,
        "expected_status": ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
        "confirmation": "APROBAR ENVIO A NIA",
    }
    values.update(changes)
    return ReviewDecisionIntent(**values)


class ReviewPrincipalTests(unittest.TestCase):
    def test_principal_is_trimmed_frozen_and_normalized_to_utc(self):
        value = principal(actor="  hugo  ", credential_id=" reviewer:hugo:v1 ")

        self.assertEqual(value.actor, "hugo")
        self.assertEqual(value.credential_id, "reviewer:hugo:v1")
        self.assertEqual(
            value.authenticated_at,
            datetime(2026, 7, 22, 17, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValidationError):
            value.actor = "otro"

    def test_principal_rejects_naive_time_and_unsafe_credential_id(self):
        with self.assertRaisesRegex(ValidationError, "zona horaria"):
            principal(authenticated_at=datetime(2026, 7, 22, 12, 0))
        with self.assertRaisesRegex(ValidationError, "identificador no secreto"):
            principal(credential_id="Bearer secret value")
        with self.assertRaisesRegex(ValidationError, "caracteres de control"):
            principal(actor="hugo\nadmin")


class ReviewDecisionIntentTests(unittest.TestCase):
    def test_intent_accepts_only_client_fields_and_normalizes_reason(self):
        value = intent(reason="  verificado con el cliente  ")

        self.assertEqual(value.reason, "verificado con el cliente")
        self.assertEqual(value.decision_id, DECISION_ID)
        with self.assertRaises(ValidationError):
            ReviewDecisionIntent(
                **value.model_dump(),
                actor="actor-controlado-por-cliente",
            )

    def test_intent_rejects_invalid_identifiers_extras_and_secret_reason(self):
        cases = (
            {"content_hash": "not-a-hash"},
            {"decision_id": "not-a-uuid"},
            {"decision_id": UUID("12345678-1234-1678-9234-567812345678")},
            {"reason": "token=valor-secreto"},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                intent(**changes)

        with self.assertRaises(ValidationError):
            ReviewDecisionIntent(
                **intent().model_dump(),
                unexpected="blocked",
            )


class BindReviewDecisionTests(unittest.TestCase):
    def test_all_four_actions_bind_expected_stage_decision_and_status(self):
        cases = (
            (
                ReviewDecisionAction.APPROVE_INPUT,
                ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
                "APROBAR ENVIO A NIA",
                None,
                ReviewDecisionStage.INPUT,
                ReviewDecisionValue.APPROVED,
            ),
            (
                ReviewDecisionAction.REJECT_INPUT,
                ReviewExpectedStatus.NEEDS_INPUT_REVIEW,
                "RECHAZAR ENTRADA",
                "fuera de alcance",
                ReviewDecisionStage.INPUT,
                ReviewDecisionValue.REJECTED,
            ),
            (
                ReviewDecisionAction.APPROVE_OUTPUT,
                ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
                "APROBAR ENVIO A BITRIX",
                None,
                ReviewDecisionStage.OUTPUT,
                ReviewDecisionValue.APPROVED,
            ),
            (
                ReviewDecisionAction.REJECT_OUTPUT,
                ReviewExpectedStatus.NEEDS_OUTPUT_REVIEW,
                "RECHAZAR SALIDA",
                "respuesta no aprobada",
                ReviewDecisionStage.OUTPUT,
                ReviewDecisionValue.REJECTED,
            ),
        )
        for action, status, confirmation, reason, stage, decision in cases:
            with self.subTest(action=action):
                command = bind_review_decision(
                    event_key=EVENT_KEY,
                    action=action,
                    intent=intent(
                        expected_status=status,
                        confirmation=confirmation,
                        reason=reason,
                    ),
                    principal=principal(),
                )
                self.assertEqual(command.stage, stage)
                self.assertEqual(command.decision, decision)
                self.assertEqual(command.principal.actor, "hugo")

    def test_binding_rejects_stale_stage_wrong_phrase_and_reasonless_rejection(self):
        cases = (
            (
                ReviewDecisionAction.APPROVE_OUTPUT,
                intent(),
                "review_expected_status_mismatch",
            ),
            (
                ReviewDecisionAction.APPROVE_INPUT,
                intent(confirmation="APROBAR ENVIO A BITRIX"),
                "review_confirmation_mismatch",
            ),
            (
                ReviewDecisionAction.REJECT_INPUT,
                intent(confirmation="RECHAZAR ENTRADA"),
                "review_rejection_reason_required",
            ),
        )
        for action, value, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                bind_review_decision(
                    event_key=EVENT_KEY,
                    action=action,
                    intent=value,
                    principal=principal(),
                )

    def test_semantic_fingerprint_is_stable_and_detects_meaning_changes(self):
        first = bind_review_decision(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            intent=intent(),
            principal=principal(),
        )
        repeated_after_reauthentication = bind_review_decision(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            intent=intent(),
            principal=principal(
                authenticated_at=datetime(2026, 7, 22, 18, tzinfo=timezone.utc)
            ),
        )
        changed = bind_review_decision(
            event_key=EVENT_KEY,
            action=ReviewDecisionAction.APPROVE_INPUT,
            intent=intent(reason="decisión documentada"),
            principal=principal(),
        )

        self.assertEqual(
            first.semantic_fingerprint(),
            repeated_after_reauthentication.semantic_fingerprint(),
        )
        self.assertNotEqual(
            first.semantic_fingerprint(),
            changed.semantic_fingerprint(),
        )
        self.assertRegex(first.semantic_fingerprint(), r"^[a-f0-9]{64}$")


if __name__ == "__main__":
    unittest.main()
