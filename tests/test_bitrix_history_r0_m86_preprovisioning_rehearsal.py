import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_MAGIC,
    MAX_M84_BLOB_BYTES,
)
from bitrix_connector.bitrix_history_r0_m86_preprovisioning_rehearsal import (
    InjectedProtectedOriginFixture,
    M86AAPreProvisioningRehearsal,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-aa-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


def over_limit_buffers():
    overhead = len(M84_BLOB_MAGIC) + sum(
        2 + len(name.encode("ascii")) + 4 for name in PROTECTED_SETTING_NAMES
    )
    values = {name: bytearray(b"x") for name in PROTECTED_SETTING_NAMES}
    values[PROTECTED_SETTING_NAMES[0]].extend(
        b"x" * (MAX_M84_BLOB_BYTES - overhead - len(PROTECTED_SETTING_NAMES) + 1)
    )
    return values


class M86AAPreProvisioningRehearsalTests(unittest.TestCase):
    def test_single_transfer_materializes_fit_candidate_and_cleans_everything(self):
        buffers = fixture_buffers()
        retained = tuple(buffers.values())
        source = InjectedProtectedOriginFixture(buffers=buffers)
        result = M86AAPreProvisioningRehearsal().run_once(source=source)
        self.assertEqual((result.state, result.failure_category), ("READY-INERT", "none"))
        self.assertEqual((result.source_transfer_calls, result.materialization_calls), (1, 1))
        self.assertTrue(result.candidate_fit_verified)
        self.assertTrue(result.candidate_handoff_ready_before_cleanup)
        self.assertEqual(result.candidate_handoff_calls, 0)
        self.assertTrue(result.source_closed)
        self.assertTrue(result.input_buffers_zeroized)
        self.assertTrue(result.candidate_blob_zeroized)
        self.assertTrue(all(not any(value) for value in retained))

    def test_over_limit_is_no_go_without_target_handoff(self):
        source = InjectedProtectedOriginFixture(buffers=over_limit_buffers())
        result = M86AAPreProvisioningRehearsal().run_once(source=source)
        self.assertEqual((result.state, result.failure_category), ("NO-GO", "candidate_not_fit"))
        self.assertFalse(result.candidate_fit_verified)
        self.assertFalse(result.candidate_handoff_ready_before_cleanup)
        self.assertEqual(result.candidate_handoff_calls, 0)
        self.assertTrue(result.source_closed)
        self.assertTrue(result.input_buffers_zeroized)

    def test_missing_or_invalid_value_is_source_contract_no_go(self):
        missing = fixture_buffers()
        missing.pop(PROTECTED_SETTING_NAMES[-1])
        invalid = fixture_buffers()
        invalid[PROTECTED_SETTING_NAMES[0]] = bytearray(b"bad\x00fixture")
        for buffers in (missing, invalid):
            retained = tuple(buffers.values())
            result = M86AAPreProvisioningRehearsal().run_once(
                source=InjectedProtectedOriginFixture(buffers=buffers)
            )
            self.assertEqual(result.failure_category, "source_contract_invalid")
            self.assertTrue(result.input_buffers_zeroized)
            self.assertTrue(all(not any(value) for value in retained))

    def test_rehearsal_and_source_are_one_shot(self):
        source = InjectedProtectedOriginFixture(buffers=fixture_buffers())
        rehearsal = M86AAPreProvisioningRehearsal()
        rehearsal.run_once(source=source)
        with self.assertRaisesRegex(RuntimeError, "reuse_or_source_invalid"):
            rehearsal.run_once(
                source=InjectedProtectedOriginFixture(buffers=fixture_buffers())
            )
        with self.assertRaisesRegex(RuntimeError, "origin_fixture_unavailable"):
            source.take_buffers_once()

    def test_wrong_source_type_is_rejected_before_use(self):
        with self.assertRaisesRegex(RuntimeError, "reuse_or_source_invalid"):
            M86AAPreProvisioningRehearsal().run_once(source=object())

    def test_public_snapshot_is_aggregate_inert_and_redacted(self):
        source = InjectedProtectedOriginFixture(buffers=fixture_buffers())
        result = M86AAPreProvisioningRehearsal().run_once(source=source)
        self.assertFalse(result.values_exposed)
        self.assertFalse(result.lengths_exposed)
        self.assertFalse(result.real_source_bound)
        self.assertEqual((result.target_calls, result.operating_system_calls, result.external_calls), (0, 0, 0))
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)
        self.assertEqual(repr(source), "InjectedProtectedOriginFixture(<redacted>)")

    def test_module_has_no_real_source_target_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_preprovisioning_rehearsal.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "path(",
            "open(",
            "ctypes",
            "windll",
            "credreadw",
            "credwritew",
            "dotenv",
            "os.environ",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
