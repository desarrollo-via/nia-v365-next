import unittest
from pathlib import Path

from bitrix_connector.bitrix_event_scoped_r1_cut_manifest import (
    resolve_m53_m86_cut_paths,
)
from bitrix_connector.bitrix_event_scoped_r1_stage_plan import (
    M53_M86_STAGE_ARGV_SHA256,
    build_m53_m86_stage_plan,
    m53_m86_stage_argv_digest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EventScopedR1StagePlanTests(unittest.TestCase):
    def test_exact_literal_plan_is_prepared_but_not_executable(self):
        paths = resolve_m53_m86_cut_paths(PROJECT_ROOT)
        result = build_m53_m86_stage_plan(PROJECT_ROOT, candidate_paths=paths)

        self.assertEqual(result.state, "PREPARED")
        self.assertEqual(result.argv[:3], ("git", "add", "--"))
        self.assertEqual(result.argv[3:], paths)
        self.assertEqual(result.path_count, 284)
        self.assertTrue(result.literal_paths_only)
        self.assertTrue(result.manifest_verified)
        self.assertTrue(result.index_unchanged)
        self.assertFalse(result.stage_authorized)
        self.assertFalse(result.executable)
        self.assertEqual((result.git_calls, result.external_calls), (0, 0))
        self.assertEqual(
            m53_m86_stage_argv_digest(result.argv),
            M53_M86_STAGE_ARGV_SHA256,
        )

    def test_candidate_drift_removes_the_entire_command(self):
        paths = resolve_m53_m86_cut_paths(PROJECT_ROOT)
        result = build_m53_m86_stage_plan(
            PROJECT_ROOT,
            candidate_paths=paths[:-1] + ("unexpected.txt",),
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.argv, ())
        self.assertEqual(result.path_count, 0)
        self.assertFalse(result.manifest_verified)
        self.assertEqual(result.git_calls, 0)

    def test_module_has_no_execution_surface(self):
        source = (
            PROJECT_ROOT
            / "bitrix_connector"
            / "bitrix_event_scoped_r1_stage_plan.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("import subprocess", source)
        self.assertNotIn("import os", source)
        self.assertNotIn("__main__", source)
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main()
