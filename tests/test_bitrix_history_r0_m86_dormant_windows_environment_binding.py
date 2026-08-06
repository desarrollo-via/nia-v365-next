import ctypes
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantBindingContract,
    M86AEDormantWindowsEnvironmentSource,
    M86AEWindowsEnvironmentBackend,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


ROOT = Path(__file__).resolve().parents[1]


class FakeWindowsEnvironmentApi:
    def __init__(self, values):
        self.values = dict(values)
        self.calls = []

    def get(self, name, target, size):
        self.calls.append(name)
        value = self.values.get(name)
        if value is None:
            return 0
        if target is None:
            return len(value) + 1
        target.value = value
        return len(value)

    def convert(self, code_page, flags, source, chars, target, size, default, used):
        raw = source.value[:chars].encode("utf-8")
        if target is None:
            return len(raw)
        ctypes.memmove(target, raw, len(raw))
        return len(raw)


def fixture_api():
    return FakeWindowsEnvironmentApi(
        {name: f"fixture-m86-ae-{index}" for index, name in enumerate(PROTECTED_SETTING_NAMES)}
    )


class M86AEDormantWindowsEnvironmentBindingTests(unittest.TestCase):
    def test_construction_is_dormant_and_contract_is_no_go(self):
        api = fixture_api()
        backend = M86AEWindowsEnvironmentBackend(
            get_environment_variable_w=api.get,
            wide_char_to_multi_byte=api.convert,
        )
        contract = M86AEDormantBindingContract()
        self.assertEqual(api.calls, [])
        self.assertEqual((contract.state, contract.current_read_budget), ("DORMANT-NO-GO", 0))
        self.assertTrue(contract.real_binding_defined)
        self.assertTrue(contract.real_factory_available)
        self.assertFalse(contract.real_factory_invoked)
        self.assertFalse(contract.real_binding_executed)
        backend.close()

    def test_exact_seven_reads_and_owned_bytearrays_with_fake_api(self):
        api = fixture_api()
        backend = M86AEWindowsEnvironmentBackend(
            get_environment_variable_w=api.get,
            wide_char_to_multi_byte=api.convert,
        )
        source = M86AEDormantWindowsEnvironmentSource(backend=backend)
        source.open_once()
        buffers = source.take_buffers_once()
        self.assertEqual(backend.calls, list(PROTECTED_SETTING_NAMES))
        self.assertEqual(api.calls[::2], list(PROTECTED_SETTING_NAMES))
        self.assertEqual(api.calls[1::2], list(PROTECTED_SETTING_NAMES))
        self.assertTrue(all(type(value) is bytearray for value in buffers.values()))
        retained = tuple(buffers.values())
        for value in buffers.values():
            value[:] = b"\x00" * len(value)
        buffers.clear()
        source.close()
        self.assertTrue(all(not any(value) for value in retained))

    def test_missing_value_fails_closed_and_closes(self):
        api = fixture_api()
        api.values.pop(PROTECTED_SETTING_NAMES[-1])
        source = M86AEDormantWindowsEnvironmentSource(
            backend=M86AEWindowsEnvironmentBackend(
                get_environment_variable_w=api.get,
                wide_char_to_multi_byte=api.convert,
            )
        )
        with self.assertRaisesRegex(ValueError, "exact_value_unavailable"):
            source.open_once()
        self.assertTrue(source.resources_closed)

    def test_unknown_and_repeated_names_are_blocked(self):
        api = fixture_api()
        backend = M86AEWindowsEnvironmentBackend(
            get_environment_variable_w=api.get,
            wide_char_to_multi_byte=api.convert,
        )
        with self.assertRaisesRegex(RuntimeError, "exact_read_blocked"):
            backend.take_exact_once("UNKNOWN")
        value = backend.take_exact_once(PROTECTED_SETTING_NAMES[0])
        value[:] = b"\x00" * len(value)
        with self.assertRaisesRegex(RuntimeError, "exact_read_blocked"):
            backend.take_exact_once(PROTECTED_SETTING_NAMES[0])
        backend.close()

    def test_module_has_no_enumeration_fallback_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_dormant_windows_environment_binding.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "os.getenv",
            "environw",
            "getenvironmentstrings",
            "dotenv",
            "credread",
            "credwrite",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("wintypes.lpcwch", source)
        self.assertNotIn("wintypes.lpcch", source)


if __name__ == "__main__":
    unittest.main()
