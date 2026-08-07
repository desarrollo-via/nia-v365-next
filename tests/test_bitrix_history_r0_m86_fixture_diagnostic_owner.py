import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_fixture_diagnostic_owner import (
    M86AMFixtureDiagnosticOwner,
    M86AMFixtureOperations,
)


ROOT = Path(__file__).resolve().parents[1]


class M86AMFixtureDiagnosticOwnerTests(unittest.TestCase):
    def test_fit_path(self):
        result = M86AMFixtureDiagnosticOwner().run_once(
            operations=M86AMFixtureOperations()
        )
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))

    def test_authorization_category(self):
        result = M86AMFixtureDiagnosticOwner().run_once(
            operations=M86AMFixtureOperations(authorization_exact=False)
        )
        self.assertEqual(result.failure_category, "authorization_invalid")

    def test_all_source_failures_are_aggregate(self):
        for stage in ("factory_failed", "open_failed", "transfer_failed"):
            result = M86AMFixtureDiagnosticOwner().run_once(
                operations=M86AMFixtureOperations(source_stage=stage)
            )
            self.assertEqual(result.failure_category, "source_aggregate_unavailable")

    def test_candidate_categories(self):
        not_fit = M86AMFixtureDiagnosticOwner().run_once(
            operations=M86AMFixtureOperations(candidate_stage="not_fit")
        )
        failed = M86AMFixtureDiagnosticOwner().run_once(
            operations=M86AMFixtureOperations(candidate_stage="composition_failed")
        )
        self.assertEqual(not_fit.failure_category, "candidate_not_fit")
        self.assertEqual(failed.failure_category, "composition_failed")

    def test_cleanup_ambiguity_overrides_prior_result(self):
        result = M86AMFixtureDiagnosticOwner().run_once(
            operations=M86AMFixtureOperations(cleanup_verified=False)
        )
        self.assertEqual(result.failure_category, "cleanup_ambiguous")

    def test_owner_is_one_shot(self):
        owner = M86AMFixtureDiagnosticOwner()
        owner.run_once(operations=M86AMFixtureOperations())
        with self.assertRaisesRegex(RuntimeError, "reuse_or_operations_invalid"):
            owner.run_once(operations=M86AMFixtureOperations())

    def test_module_has_no_real_source_or_service_surface(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_m86_fixture_diagnostic_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "getenvironmentvariable",
            "ctypes",
            "dotenv",
            "credread",
            "httpx",
            "pymongo",
            "subprocess",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
