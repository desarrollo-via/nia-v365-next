import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_MAGIC,
    MAX_M84_BLOB_BYTES,
)
from bitrix_connector.bitrix_history_r0_m86_aggregate_fit_probe import (
    M86YAggregateFitProbe,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-y-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


def exact_limit_buffers(*, extra=0):
    overhead = len(M84_BLOB_MAGIC) + sum(
        2 + len(name.encode("ascii")) + 4 for name in PROTECTED_SETTING_NAMES
    )
    payload_size = MAX_M84_BLOB_BYTES - overhead + extra
    values = {name: bytearray(b"x") for name in PROTECTED_SETTING_NAMES}
    values[PROTECTED_SETTING_NAMES[0]].extend(
        b"x" * (payload_size - len(PROTECTED_SETTING_NAMES))
    )
    return values


class M86YAggregateFitProbeTests(unittest.TestCase):
    def test_exact_limit_returns_only_aggregate_fit_and_zeroizes(self):
        buffers = exact_limit_buffers()
        retained = tuple(buffers.values())
        result = M86YAggregateFitProbe().probe_once(buffers=buffers)
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))
        self.assertTrue(result.required_buffer_set_present)
        self.assertTrue(result.fits_native_blob_limit)
        self.assertTrue(result.input_buffers_zeroized)
        self.assertTrue(result.candidate_blob_zeroized)
        self.assertTrue(all(not any(value) for value in retained))
        self.assertEqual(buffers, {})

    def test_one_extra_byte_returns_closed_limit_category(self):
        buffers = exact_limit_buffers(extra=1)
        retained = tuple(buffers.values())
        result = M86YAggregateFitProbe().probe_once(buffers=buffers)
        self.assertEqual(
            (result.state, result.failure_category),
            ("NO-GO", "native_blob_limit_exceeded"),
        )
        self.assertTrue(result.required_buffer_set_present)
        self.assertFalse(result.fits_native_blob_limit)
        self.assertTrue(result.input_buffers_zeroized)
        self.assertTrue(all(not any(value) for value in retained))

    def test_missing_or_reordered_buffers_fail_contract_and_are_cleaned(self):
        missing = fixture_buffers()
        missing.pop(PROTECTED_SETTING_NAMES[-1])
        reordered = fixture_buffers()
        first = reordered.pop(PROTECTED_SETTING_NAMES[0])
        reordered[PROTECTED_SETTING_NAMES[0]] = first
        for buffers in (missing, reordered):
            retained = tuple(buffers.values())
            result = M86YAggregateFitProbe().probe_once(buffers=buffers)
            self.assertEqual(result.failure_category, "buffer_contract_invalid")
            self.assertFalse(result.required_buffer_set_present)
            self.assertTrue(result.input_buffers_zeroized)
            self.assertTrue(all(not any(value) for value in retained))

    def test_invalid_value_has_closed_category_and_cleanup(self):
        buffers = fixture_buffers()
        buffers[PROTECTED_SETTING_NAMES[0]] = bytearray(b"bad\x00fixture")
        retained = tuple(buffers.values())
        result = M86YAggregateFitProbe().probe_once(buffers=buffers)
        self.assertEqual(result.failure_category, "buffer_value_invalid")
        self.assertTrue(result.required_buffer_set_present)
        self.assertTrue(result.input_buffers_zeroized)
        self.assertTrue(all(not any(value) for value in retained))

    def test_probe_is_one_shot(self):
        probe = M86YAggregateFitProbe()
        probe.probe_once(buffers=fixture_buffers())
        with self.assertRaisesRegex(RuntimeError, "probe_reused"):
            probe.probe_once(buffers=fixture_buffers())

    def test_snapshot_exposes_no_values_lengths_source_or_effects(self):
        result = M86YAggregateFitProbe().probe_once(buffers=fixture_buffers())
        self.assertFalse(result.values_exposed)
        self.assertFalse(result.individual_lengths_exposed)
        self.assertFalse(result.aggregate_length_exposed)
        self.assertFalse(result.real_source_bound)
        self.assertEqual((result.operating_system_calls, result.external_calls), (0, 0))
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_module_has_no_real_source_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_aggregate_fit_probe.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
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
