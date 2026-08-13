import unittest
from pathlib import Path

from bitrix_connector.r1_key_vault_draft_pr_effects_audit import (
    EXPECTED_HEAD,
    EXPECTED_SHA,
    EffectsAuditInputError,
    EffectsAuditTransportError,
    collect_effects_once,
    evaluate_effects_payloads,
)


ROOT = Path(__file__).resolve().parents[1]


def pr(number):
    return {"number": number, "head": {"ref": EXPECTED_HEAD, "sha": EXPECTED_SHA}}


def payloads(**overrides):
    value = {
        "head_prs": [],
        "commit_prs": [],
        "actions": {"total_count": 0},
        "checks": {"total_count": 0},
        "statuses": {"statuses": []},
    }
    value.update(overrides)
    return value


class FakeTransport:
    def __init__(self, values=None, error_at=None):
        self.values = list(values or [])
        self.error_at = error_at
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        if self.error_at == len(self.urls):
            raise RuntimeError("private transport detail")
        return 200, self.values[len(self.urls) - 1]


class R1DraftPrEffectsAuditTests(unittest.TestCase):
    def test_all_zero_is_effects_absent(self):
        result = evaluate_effects_payloads(payloads())
        self.assertEqual(result.decision, "EFFECTS-ABSENT")
        self.assertEqual((result.associated_prs, result.actions, result.checks, result.statuses), (0, 0, 0, 0))

    def test_same_pr_from_two_surfaces_is_deduplicated(self):
        result = evaluate_effects_payloads(payloads(head_prs=[pr(14)], commit_prs=[pr(14)]))
        self.assertEqual(result.associated_prs, 1)

    def test_distinct_prs_are_counted(self):
        result = evaluate_effects_payloads(payloads(head_prs=[pr(14)], commit_prs=[pr(15)]))
        self.assertEqual(result.associated_prs, 2)
        self.assertEqual(result.decision, "EFFECTS-PRESENT")

    def test_each_non_pr_effect_is_visible(self):
        for label, value in (
            ("actions", {"total_count": 1}),
            ("checks", {"total_count": 2}),
            ("statuses", {"statuses": [{"id": 1}]}),
        ):
            with self.subTest(label=label):
                result = evaluate_effects_payloads(payloads(**{label: value}))
                self.assertEqual(result.decision, "EFFECTS-PRESENT")
                self.assertGreater(getattr(result, label), 0)

    def test_wrong_pr_scope_is_rejected(self):
        wrong = {"number": 14, "head": {"ref": "other", "sha": EXPECTED_SHA}}
        with self.assertRaisesRegex(EffectsAuditInputError, "scope_invalid"):
            evaluate_effects_payloads(payloads(head_prs=[wrong]))

    def test_invalid_shapes_and_counts_are_rejected(self):
        candidates = (
            {"head_prs": {}},
            {"actions": {"total_count": -1}},
            {"checks": {"total_count": "0"}},
            {"statuses": {"statuses": {}}},
        )
        for override in candidates:
            with self.subTest(override=override):
                with self.assertRaises(EffectsAuditInputError):
                    evaluate_effects_payloads(payloads(**override))

    def test_collector_calls_five_exact_gets_once(self):
        transport = FakeTransport([[], [], {"total_count": 0}, {"total_count": 0}, {"statuses": []}])
        result = collect_effects_once(transport)
        self.assertEqual(result.decision, "EFFECTS-ABSENT")
        self.assertEqual(len(transport.urls), 5)
        self.assertEqual(len(set(transport.urls)), 5)
        self.assertTrue(all(url.startswith("https://api.github.com/repos/desarrollo-via/nia-v365-next/") for url in transport.urls))

    def test_transport_failure_is_redacted_and_not_retried(self):
        transport = FakeTransport([[]], error_at=2)
        with self.assertRaisesRegex(EffectsAuditTransportError, "transport_error") as raised:
            collect_effects_once(transport)
        self.assertNotIn("private", str(raised.exception))
        self.assertEqual(len(transport.urls), 2)

    def test_source_has_no_mutation_auth_or_raw_payload_output(self):
        text = (ROOT / "bitrix_connector" / "r1_key_vault_draft_pr_effects_audit.py").read_text(encoding="utf-8").lower()
        for forbidden in ("method=\"post\"", "method=\"put\"", "method=\"delete\"", "authorization", "subprocess", "gh ", "token", "print(payload"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
