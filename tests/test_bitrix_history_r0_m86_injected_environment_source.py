import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_injected_environment_source import (
    InjectedExactEnvironmentAccessor,
    M86ACInjectedEnvironmentContract,
    M86ACInjectedEnvironmentSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-ac-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


class M86ACInjectedEnvironmentSourceTests(unittest.TestCase):
    def test_reads_exact_names_once_and_transfers_owned_buffers(self):
        original = fixture_buffers()
        retained = tuple(original.values())
        accessor = InjectedExactEnvironmentAccessor(buffers=original)
        source = M86ACInjectedEnvironmentSource(accessor=accessor)
        source.open_once()
        buffers = source.take_buffers_once()
        self.assertEqual(accessor.calls, list(PROTECTED_SETTING_NAMES))
        self.assertEqual(tuple(buffers), PROTECTED_SETTING_NAMES)
        self.assertEqual(tuple(buffers.values()), retained)
        for value in buffers.values():
            value[:] = b"\x00" * len(value)
        buffers.clear()
        source.close()
        self.assertEqual(accessor.close_calls, 1)

    def test_missing_value_fails_and_zeroizes_partial_buffers(self):
        original = fixture_buffers()
        original.pop(PROTECTED_SETTING_NAMES[-1])
        retained = tuple(original.values())
        accessor = InjectedExactEnvironmentAccessor(buffers=original)
        source = M86ACInjectedEnvironmentSource(accessor=accessor)
        with self.assertRaisesRegex(ValueError, "exact_buffer_invalid"):
            source.open_once()
        self.assertTrue(all(not any(value) for value in retained))
        self.assertEqual(accessor.close_calls, 1)

    def test_nul_value_fails_and_zeroizes_everything(self):
        original = fixture_buffers()
        original[PROTECTED_SETTING_NAMES[2]] = bytearray(b"bad\x00fixture")
        retained = tuple(original.values())
        source = M86ACInjectedEnvironmentSource(
            accessor=InjectedExactEnvironmentAccessor(buffers=original)
        )
        with self.assertRaisesRegex(ValueError, "exact_buffer_invalid"):
            source.open_once()
        self.assertTrue(all(not any(value) for value in retained))

    def test_source_accessor_and_names_are_one_shot(self):
        accessor = InjectedExactEnvironmentAccessor(buffers=fixture_buffers())
        source = M86ACInjectedEnvironmentSource(accessor=accessor)
        source.open_once()
        buffers = source.take_buffers_once()
        with self.assertRaisesRegex(RuntimeError, "source_unavailable"):
            source.open_once()
        with self.assertRaisesRegex(RuntimeError, "read_blocked"):
            accessor.take_exact_once(PROTECTED_SETTING_NAMES[0])
        for value in buffers.values():
            value[:] = b"\x00" * len(value)
        source.close()

    def test_close_before_take_zeroizes_retained_buffers(self):
        original = fixture_buffers()
        retained = tuple(original.values())
        source = M86ACInjectedEnvironmentSource(
            accessor=InjectedExactEnvironmentAccessor(buffers=original)
        )
        source.open_once()
        source.close()
        self.assertTrue(all(not any(value) for value in retained))

    def test_contract_and_repr_confirm_fixture_only_boundary(self):
        accessor = InjectedExactEnvironmentAccessor(buffers=fixture_buffers())
        source = M86ACInjectedEnvironmentSource(accessor=accessor)
        contract = M86ACInjectedEnvironmentContract()
        self.assertEqual((contract.phase, contract.state), ("M86-AC", "FIXTURE-ONLY"))
        self.assertEqual((contract.exact_read_budget, contract.enumeration_budget), (7, 0))
        self.assertEqual(contract.fallback_budget, 0)
        self.assertFalse(contract.real_environment_binding_present)
        self.assertFalse(contract.immutable_string_handoff_allowed)
        self.assertTrue(contract.owned_bytearray_handoff_required)
        self.assertTrue(contract.close_and_zeroize_required)
        self.assertEqual((contract.operating_system_calls, contract.external_calls), (0, 0))
        self.assertEqual(repr(accessor), "InjectedExactEnvironmentAccessor(<redacted>)")
        self.assertEqual(repr(source), "M86ACInjectedEnvironmentSource(<redacted>)")
        source.close()

    def test_module_has_no_real_environment_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_injected_environment_source.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "getenv",
            "environ[",
            "path(",
            "open(",
            "ctypes",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
