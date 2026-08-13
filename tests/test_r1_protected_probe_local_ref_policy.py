import unittest

from bitrix_connector.r1_protected_probe_local_ref_policy import (
    LocalRefDecision,
    LocalRefPhase,
    evaluate_local_ref_transition,
)


CANDIDATE = "d" * 40
OTHER = "a" * 40
BRANCH = "codex/r1-keyvault-protected-probe-v0580"
TRACKING = f"refs/remotes/origin/{BRANCH}"
OWN = f"refs/heads/{BRANCH}"
BASELINE = {
    "refs/heads/main": OTHER,
    "refs/remotes/origin/main": OTHER,
}


def evaluate(after, phase=LocalRefPhase.PUBLISHED, before=None):
    return evaluate_local_ref_transition(
        before=BASELINE if before is None else before,
        after=after,
        branch=BRANCH,
        candidate_sha=CANDIDATE,
        phase=phase,
    )


class R1ProtectedProbeLocalRefPolicyTests(unittest.TestCase):
    def test_success_accepts_exact_origin_tracking_ref(self):
        after = {**BASELINE, TRACKING: CANDIDATE}
        self.assertEqual(
            evaluate(after),
            LocalRefDecision.EXACT_WITH_TRACKING,
        )

    def test_success_also_accepts_no_tracking_ref(self):
        self.assertEqual(
            evaluate(BASELINE),
            LocalRefDecision.EXACT_WITHOUT_TRACKING,
        )

    def test_local_branch_is_drift_even_at_candidate(self):
        self.assertEqual(
            evaluate({**BASELINE, OWN: CANDIDATE}),
            LocalRefDecision.REF_DRIFT,
        )

    def test_tracking_ref_with_wrong_sha_is_drift(self):
        self.assertEqual(
            evaluate({**BASELINE, TRACKING: OTHER}),
            LocalRefDecision.REF_DRIFT,
        )

    def test_unrelated_ref_addition_change_or_removal_is_drift(self):
        states = (
            {**BASELINE, "refs/heads/unexpected": OTHER},
            {**BASELINE, "refs/heads/main": CANDIDATE},
            {"refs/heads/main": OTHER},
        )
        for after in states:
            with self.subTest(after=after):
                self.assertEqual(evaluate(after), LocalRefDecision.REF_DRIFT)

    def test_preexisting_candidate_refs_invalidate_baseline(self):
        for name in (OWN, TRACKING):
            with self.subTest(name=name):
                before = {**BASELINE, name: CANDIDATE}
                self.assertEqual(
                    evaluate(before, before=before),
                    LocalRefDecision.BASELINE_INVALID,
                )

    def test_rollback_requires_literal_baseline_restoration(self):
        self.assertEqual(
            evaluate(BASELINE, phase=LocalRefPhase.ROLLED_BACK),
            LocalRefDecision.EXACT_RESTORED,
        )
        self.assertEqual(
            evaluate(
                {**BASELINE, TRACKING: CANDIDATE},
                phase=LocalRefPhase.ROLLED_BACK,
            ),
            LocalRefDecision.REF_DRIFT,
        )

    def test_invalid_branch_or_candidate_sha_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidate_branch_invalid"):
            evaluate_local_ref_transition(
                before=BASELINE,
                after=BASELINE,
                branch="refs/heads/not-allowed",
                candidate_sha=CANDIDATE,
                phase=LocalRefPhase.PUBLISHED,
            )
        with self.assertRaisesRegex(ValueError, "candidate_sha_invalid"):
            evaluate_local_ref_transition(
                before=BASELINE,
                after=BASELINE,
                branch=BRANCH,
                candidate_sha="short",
                phase=LocalRefPhase.PUBLISHED,
            )

    def test_invalid_snapshot_or_phase_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "local_ref_name_invalid"):
            evaluate({"main": OTHER})
        with self.assertRaisesRegex(TypeError, "local_ref_phase_invalid"):
            evaluate_local_ref_transition(
                before=BASELINE,
                after=BASELINE,
                branch=BRANCH,
                candidate_sha=CANDIDATE,
                phase="published",
            )


if __name__ == "__main__":
    unittest.main()
