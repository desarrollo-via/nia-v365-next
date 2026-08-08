import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_MAGIC,
    MAX_M84_BLOB_BYTES,
)
from bitrix_connector.bitrix_history_r0_m86_injected_environment_preprovisioning import (
    M86ADInjectedEnvironmentPreProvisioningOwner,
)
from bitrix_connector.bitrix_history_r0_m86_injected_environment_source import (
    InjectedExactEnvironmentAccessor,
    M86ACInjectedEnvironmentSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-ad-{index}".encode("ascii"))
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


def source_from(buffers):
    return M86ACInjectedEnvironmentSource(
        accessor=InjectedExactEnvironmentAccessor(buffers=buffers)
    )


class M86ADInjectedEnvironmentPreProvisioningTests(unittest.TestCase):
    def test_exact_seven_reads_one_transfer_one_materialization_ready_inert(self):
        original = fixture_buffers()
        retained = tuple(original.values())
        result = M86ADInjectedEnvironmentPreProvisioningOwner().run_once(
            source=source_from(original)
        )
        self.assertEqual((result.state, result.failure_category), ("READY-INERT", "none"))
        self.assertEqual(
            (
                result.source_open_calls,
                result.exact_name_read_calls,
                result.buffer_transfer_calls,
                result.materialization_calls,
            ),
            (1, 7, 1, 1),
        )
        self.assertTrue(result.candidate_fit_verified)
        self.assertEqual(result.target_handoff_calls, 0)
        self.assertTrue(result.source_closed)
        self.assertTrue(result.input_buffers_zeroized)
        self.assertTrue(result.candidate_blob_zeroized)
        self.assertTrue(all(not any(value) for value in retained))

    def test_over_limit_is_no_go_before_target(self):
        result = M86ADInjectedEnvironmentPreProvisioningOwner().run_once(
            source=source_from(over_limit_buffers())
        )
        self.assertEqual((result.state, result.failure_category), ("NO-GO", "candidate_not_fit"))
        self.assertEqual(result.target_handoff_calls, 0)
        self.assertTrue(result.source_closed)
        self.assertTrue(result.input_buffers_zeroized)

    def test_missing_and_invalid_values_are_source_invalid(self):
        missing = fixture_buffers()
        missing.pop(PROTECTED_SETTING_NAMES[-1])
        invalid = fixture_buffers()
        invalid[PROTECTED_SETTING_NAMES[1]] = bytearray(b"bad\x00fixture")
        for values in (missing, invalid):
            retained = tuple(values.values())
            result = M86ADInjectedEnvironmentPreProvisioningOwner().run_once(
                source=source_from(values)
            )
            self.assertEqual(result.failure_category, "source_invalid")
            self.assertTrue(result.source_closed)
            self.assertTrue(all(not any(value) for value in retained))

    def test_owner_is_one_shot(self):
        owner = M86ADInjectedEnvironmentPreProvisioningOwner()
        owner.run_once(source=source_from(fixture_buffers()))
        with self.assertRaisesRegex(RuntimeError, "reuse_or_source_invalid"):
            owner.run_once(source=source_from(fixture_buffers()))

    def test_wrong_source_type_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "reuse_or_source_invalid"):
            M86ADInjectedEnvironmentPreProvisioningOwner().run_once(source=object())

    def test_snapshot_is_redacted_and_has_no_real_effects(self):
        result = M86ADInjectedEnvironmentPreProvisioningOwner().run_once(
            source=source_from(fixture_buffers())
        )
        self.assertFalse(result.values_exposed)
        self.assertFalse(result.lengths_exposed)
        self.assertFalse(result.real_environment_bound)
        self.assertEqual((result.operating_system_calls, result.external_calls), (0, 0))
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)

    def test_module_has_no_real_environment_target_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_injected_environment_preprovisioning.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "getenv",
            "ctypes",
            "windll",
            "credwritew",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
