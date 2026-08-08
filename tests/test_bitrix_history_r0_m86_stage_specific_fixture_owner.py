import unittest

from bitrix_connector.bitrix_history_r0_m86_stage_specific_fixture_owner import (
    M86AS_FIXTURE_CONFIRMATION,
    M86ASStageSpecificFixtureOwner,
)


class FixtureSource:
    def __init__(self, *, fail_at=None):
        self.fail_at = fail_at
        self.closed = False
        self.value = bytearray(b"fixture-secret")

    def open_once(self):
        if self.fail_at == "open":
            raise RuntimeError("fixture-open")

    def take_buffers_once(self):
        if self.fail_at == "transfer":
            raise RuntimeError("fixture-transfer")
        return {"fixture": self.value}

    def close(self):
        self.closed = True
        if self.fail_at == "cleanup":
            raise RuntimeError("fixture-cleanup")


class M86ASStageSpecificFixtureOwnerTests(unittest.TestCase):
    def test_preview_never_calls_fixture_factory(self):
        calls = []
        preview = M86ASStageSpecificFixtureOwner(
            source_factory=lambda: calls.append("forbidden")
        ).preview()
        self.assertEqual((preview.state, calls), ("FIXTURE-DORMANT", []))
        self.assertFalse(preview.real_source_bound)

    def test_wrong_confirmation_does_not_call_factory(self):
        calls = []
        result = M86ASStageSpecificFixtureOwner(
            source_factory=lambda: calls.append("forbidden")
        ).run_once(confirm_code="sp")
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertEqual(calls, [])

    def test_factory_failure_has_specific_category(self):
        def broken_factory():
            raise RuntimeError("fixture-factory")

        result = M86ASStageSpecificFixtureOwner(
            source_factory=broken_factory
        ).run_once(confirm_code=M86AS_FIXTURE_CONFIRMATION)
        self.assertEqual(result.failure_category, "source_factory_unavailable")

    def test_open_failure_has_specific_category_and_closes(self):
        source = FixtureSource(fail_at="open")
        result = M86ASStageSpecificFixtureOwner(
            source_factory=lambda: source
        ).run_once(confirm_code=M86AS_FIXTURE_CONFIRMATION)
        self.assertEqual(result.failure_category, "source_open_unavailable")
        self.assertTrue(source.closed)

    def test_transfer_failure_has_specific_category_and_closes(self):
        source = FixtureSource(fail_at="transfer")
        result = M86ASStageSpecificFixtureOwner(
            source_factory=lambda: source
        ).run_once(confirm_code=M86AS_FIXTURE_CONFIRMATION)
        self.assertEqual(result.failure_category, "source_transfer_unavailable")
        self.assertTrue(source.closed)

    def test_success_zeroizes_transferred_buffers_and_closes(self):
        source = FixtureSource()
        result = M86ASStageSpecificFixtureOwner(
            source_factory=lambda: source
        ).run_once(confirm_code=M86AS_FIXTURE_CONFIRMATION)
        self.assertEqual((result.state, result.failure_category), ("SOURCE-READY", "none"))
        self.assertEqual(source.value, b"\x00" * len(source.value))
        self.assertTrue(source.closed)

    def test_cleanup_failure_overrides_success_and_owner_is_one_shot(self):
        owner = M86ASStageSpecificFixtureOwner(
            source_factory=lambda: FixtureSource(fail_at="cleanup")
        )
        result = owner.run_once(confirm_code=M86AS_FIXTURE_CONFIRMATION)
        self.assertEqual(result.failure_category, "cleanup_ambiguous")
        with self.assertRaisesRegex(RuntimeError, "already_used"):
            owner.run_once(confirm_code=M86AS_FIXTURE_CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
