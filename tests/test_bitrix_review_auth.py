import hmac
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from bitrix_connector.review_auth import (
    ReviewAuthenticationOutcome,
    ReviewAuthenticationResult,
    SingleReviewerAuthenticator,
)


TOKEN = "controlled-review-token-1234567890"


def authenticator(**changes):
    values = {
        "review_token": TOKEN,
        "actor": "hugo",
        "credential_id": "reviewer:hugo:v1",
        "clock": lambda: datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc),
    }
    values.update(changes)
    return SingleReviewerAuthenticator(**values)


class SingleReviewerAuthenticatorTests(unittest.TestCase):
    def test_exact_bearer_derives_server_principal(self):
        auth = authenticator()

        result = auth.authenticate(f"Bearer {TOKEN}")

        self.assertTrue(auth.configured)
        self.assertTrue(result.accepted)
        self.assertEqual(result.outcome, ReviewAuthenticationOutcome.AUTHENTICATED)
        self.assertEqual(result.reason, "review_authenticated")
        self.assertEqual(result.principal.actor, "hugo")
        self.assertEqual(result.principal.credential_id, "reviewer:hugo:v1")
        self.assertEqual(
            result.principal.authenticated_at,
            datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc),
        )

    def test_configured_requests_always_use_constant_time_comparison(self):
        auth = authenticator()
        headers = (
            "",
            "Basic value",
            "Bearer",
            "Bearer wrong-review-token-value",
            "Bearer contraseña-inválida",
            f"bearer {TOKEN}",
        )

        with patch(
            "bitrix_connector.review_auth.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as compared:
            results = [auth.authenticate(header) for header in headers]

        self.assertEqual(compared.call_count, len(headers))
        self.assertTrue(all(not result.accepted for result in results[:-1]))
        self.assertTrue(results[-1].accepted)
        self.assertTrue(
            all(
                result.reason == "review_unauthorized"
                for result in results[:-1]
            )
        )

    def test_incomplete_or_weak_configuration_fails_closed(self):
        cases = (
            {"review_token": None},
            {"review_token": "short"},
            {"actor": ""},
            {"credential_id": "credential with spaces"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                auth = authenticator(**changes)
                with patch(
                    "bitrix_connector.review_auth.hmac.compare_digest"
                ) as compared:
                    result = auth.authenticate(f"Bearer {TOKEN}")
                self.assertFalse(auth.configured)
                self.assertFalse(result.accepted)
                self.assertEqual(
                    result.outcome,
                    ReviewAuthenticationOutcome.UNAVAILABLE,
                )
                self.assertEqual(result.reason, "review_auth_not_configured")
                compared.assert_not_called()

    def test_invalid_server_clock_fails_closed_after_valid_token(self):
        auth = authenticator(clock=lambda: datetime(2026, 7, 22, 18, 0))

        result = auth.authenticate(f"Bearer {TOKEN}")

        self.assertFalse(result.accepted)
        self.assertEqual(result.outcome, ReviewAuthenticationOutcome.UNAVAILABLE)
        self.assertEqual(result.reason, "review_auth_clock_invalid")
        self.assertIsNone(result.principal)

    def test_secret_is_absent_from_authenticator_repr_and_results(self):
        auth = authenticator()
        accepted = auth.authenticate(f"Bearer {TOKEN}")
        rejected = auth.authenticate("Bearer wrong-review-token-value")

        evidence = " ".join(
            (
                repr(auth.__dict__),
                repr(auth),
                accepted.model_dump_json(),
                rejected.model_dump_json(),
            )
        )
        self.assertNotIn(TOKEN, evidence)
        self.assertNotIn("wrong-review-token-value", evidence)

    def test_result_model_cannot_claim_success_without_principal(self):
        with self.assertRaisesRegex(
            ValidationError,
            "review_auth_principal_outcome_mismatch",
        ):
            ReviewAuthenticationResult(
                outcome=ReviewAuthenticationOutcome.AUTHENTICATED,
                reason="invalid",
            )

    def test_module_does_not_load_web_database_or_http_clients(self):
        source = (
            Path(__file__).parents[1]
            / "bitrix_connector"
            / "review_auth.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("fastapi", "motor.motor_asyncio", "httpx"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
