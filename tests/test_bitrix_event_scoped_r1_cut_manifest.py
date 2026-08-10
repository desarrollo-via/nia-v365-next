import unittest
from pathlib import Path

from bitrix_connector.bitrix_event_scoped_r1_cut_manifest import (
    M53_M86_CUT_EXPECTED_COUNT,
    M53_M86_CUT_EXPECTED_SHA256,
    audit_m53_m86_cut,
    m53_m86_cut_digest,
    resolve_m53_m86_cut_paths,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EventScopedR1CutManifestTests(unittest.TestCase):
    def test_current_cut_is_exact_and_frozen(self):
        paths = resolve_m53_m86_cut_paths(PROJECT_ROOT)
        result = audit_m53_m86_cut(PROJECT_ROOT, candidate_paths=paths)

        self.assertEqual(len(paths), M53_M86_CUT_EXPECTED_COUNT)
        self.assertEqual(m53_m86_cut_digest(paths), M53_M86_CUT_EXPECTED_SHA256)
        self.assertEqual(result.state, "FROZEN")
        self.assertTrue(result.dependency_cut_frozen)
        self.assertEqual(result.resolved_count, 308)
        self.assertEqual(result.candidate_count, 308)
        self.assertEqual(result.implementation_count, 155)
        self.assertEqual(result.test_count, 149)
        self.assertEqual(result.documentation_count, 3)
        self.assertEqual(result.script_count, 1)
        self.assertEqual(result.missing_or_extra_count, 0)
        self.assertEqual(result.forbidden_count, 0)
        self.assertEqual(result.index_writes, 0)
        self.assertEqual(result.external_calls, 0)

    def test_missing_or_extra_candidate_fails_closed(self):
        paths = resolve_m53_m86_cut_paths(PROJECT_ROOT)
        result = audit_m53_m86_cut(
            PROJECT_ROOT,
            candidate_paths=paths[:-1] + ("unexpected.txt",),
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertFalse(result.dependency_cut_frozen)
        self.assertEqual(result.missing_or_extra_count, 2)

    def test_config_and_its_primary_test_are_mandatory(self):
        paths = resolve_m53_m86_cut_paths(PROJECT_ROOT)

        for required in (
            "bitrix_connector/config.py",
            "bitrix_connector/internal_identity_names.py",
            "tests/test_bitrix_connector.py",
            "tests/test_bitrix_internal_identity_names.py",
        ):
            with self.subTest(required=required):
                candidate = tuple(path for path in paths if path != required)
                result = audit_m53_m86_cut(
                    PROJECT_ROOT,
                    candidate_paths=candidate,
                )
                self.assertEqual(result.state, "NO-GO")
                self.assertFalse(result.dependency_cut_frozen)
                self.assertEqual(result.missing_or_extra_count, 1)


if __name__ == "__main__":
    unittest.main()
