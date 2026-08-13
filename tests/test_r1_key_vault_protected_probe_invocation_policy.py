import unittest

from bitrix_connector.r1_key_vault_protected_probe_invocation_policy import (
    EXPECTED_PACKAGES,
    ProtectedProbeInvocationState as State,
    evaluate_protected_probe_result,
)


def evidence(*, present=False, valid=None):
    return {
        "schema": "nia-next-r1-host-probe-v1",
        "packages": dict(EXPECTED_PACKAGES),
        "setting_present": present,
        "setting_valid": valid,
        "external_calls": 0,
        "writes": 0,
    }


class R1KeyVaultProtectedProbeInvocationPolicyTests(unittest.TestCase):
    def classify(self, status, payload, may_reach=True):
        return evaluate_protected_probe_result(
            status_code=status,
            payload=payload,
            request_may_have_reached_host=may_reach,
        )

    def test_accepts_only_two_exact_success_baselines(self):
        self.assertEqual(self.classify(200, evidence()), State.VERIFIED_ABSENT)
        self.assertEqual(
            self.classify(200, evidence(present=True, valid=True)),
            State.VERIFIED_PRESENT,
        )

    def test_rejects_success_schema_or_type_drift(self):
        variants = []
        for key, value in (
            ("schema", "other"),
            ("setting_present", 0),
            ("setting_valid", False),
            ("external_calls", False),
            ("writes", 1),
        ):
            candidate = evidence()
            candidate[key] = value
            variants.append(candidate)
        extra = evidence()
        extra["private"] = "detail"
        variants.append(extra)
        wrong_package = evidence()
        wrong_package["packages"]["aiohttp"] = "0.0.0"
        variants.append(wrong_package)
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    self.classify(200, candidate), State.RESPONSE_DRIFT
                )

    def test_classifies_exact_non_consuming_failures(self):
        for status, detail, expected in (
            (401, "review_unauthorized", State.AUTH_REJECTED_NOT_CONSUMED),
            (
                503,
                "review_token_not_configured",
                State.TOKEN_NOT_CONFIGURED_NOT_CONSUMED,
            ),
            (503, "host_probe_not_bound", State.PROBE_NOT_BOUND_NOT_CONSUMED),
        ):
            with self.subTest(detail=detail):
                self.assertEqual(
                    self.classify(status, {"detail": detail}), expected
                )

    def test_classifies_exact_consumed_failures(self):
        self.assertEqual(
            self.classify(503, {"detail": "host_probe_evidence_unavailable"}),
            State.CONSUMED_FAILURE,
        )
        self.assertEqual(
            self.classify(409, {"detail": "host_probe_already_consumed"}),
            State.ALREADY_CONSUMED,
        )

    def test_transport_uncertainty_never_becomes_retryable(self):
        self.assertEqual(self.classify(None, None), State.AMBIGUOUS_CONSUMPTION)
        self.assertEqual(self.classify(None, None, False), State.NOT_SENT)

    def test_error_payload_drift_fails_closed(self):
        for payload in (
            {"detail": "review_unauthorized", "extra": True},
            {"detail": "private failure"},
            None,
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.classify(401, payload), State.RESPONSE_DRIFT
                )


if __name__ == "__main__":
    unittest.main()
