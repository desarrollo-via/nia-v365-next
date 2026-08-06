import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_owned_buffer_provisioning import (
    M86AZInjectedOwnedBufferProvider,
    M86AZOwnedBufferProvisioningContract,
    M86AZOwnedBufferProvisioningSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-az-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


class M86AZOwnedBufferProvisioningTests(unittest.TestCase):
    def test_transfers_exact_aggregate_once_without_copying(self):
        original = fixture_buffers()
        retained = tuple(original.values())
        provider = M86AZInjectedOwnedBufferProvider(buffers=original)
        source = M86AZOwnedBufferProvisioningSource(provider=provider)

        source.open_once()
        buffers = source.take_buffers_once()

        self.assertEqual(provider.take_calls, 1)
        self.assertEqual(tuple(buffers), PROTECTED_SETTING_NAMES)
        self.assertEqual(tuple(buffers.values()), retained)
        _zeroize_for_test(buffers)
        source.close()
        self.assertEqual(provider.close_calls, 1)

    def test_missing_extra_and_invalid_aggregates_fail_closed(self):
        cases = []
        missing = fixture_buffers()
        missing.pop(PROTECTED_SETTING_NAMES[-1])
        cases.append(missing)
        extra = fixture_buffers()
        extra["UNEXPECTED"] = bytearray(b"fixture")
        cases.append(extra)
        invalid = fixture_buffers()
        invalid[PROTECTED_SETTING_NAMES[2]] = bytearray(b"bad\x00fixture")
        cases.append(invalid)

        for original in cases:
            with self.subTest(keys=tuple(original)):
                retained = tuple(original.values())
                provider = M86AZInjectedOwnedBufferProvider(buffers=original)
                source = M86AZOwnedBufferProvisioningSource(provider=provider)
                with self.assertRaisesRegex(ValueError, "aggregate_invalid"):
                    source.open_once()
                self.assertTrue(source.resources_closed)
                self.assertEqual(provider.close_calls, 1)
                self.assertTrue(all(not any(value) for value in retained))

    def test_source_and_provider_are_one_shot(self):
        provider = M86AZInjectedOwnedBufferProvider(buffers=fixture_buffers())
        source = M86AZOwnedBufferProvisioningSource(provider=provider)
        source.open_once()
        buffers = source.take_buffers_once()
        with self.assertRaisesRegex(RuntimeError, "source_unavailable"):
            source.open_once()
        with self.assertRaisesRegex(RuntimeError, "provider_unavailable"):
            provider.take_all_once()
        _zeroize_for_test(buffers)
        source.close()

    def test_close_before_transfer_zeroizes_owned_buffers(self):
        original = fixture_buffers()
        retained = tuple(original.values())
        source = M86AZOwnedBufferProvisioningSource(
            provider=M86AZInjectedOwnedBufferProvider(buffers=original)
        )
        source.open_once()
        source.close()
        self.assertTrue(all(not any(value) for value in retained))

    def test_contract_is_inert_and_redacted(self):
        contract = M86AZOwnedBufferProvisioningContract()
        self.assertEqual((contract.phase, contract.state), ("M86-AZ", "FIXTURE-ONLY-INERT"))
        self.assertEqual(
            (contract.provider_take_budget, contract.aggregate_name_count, contract.buffer_transfer_budget),
            (1, 7, 1),
        )
        self.assertEqual((contract.enumeration_budget, contract.fallback_budget), (0, 0))
        self.assertTrue(contract.same_process_required)
        self.assertTrue(contract.owned_bytearrays_required)
        self.assertTrue(contract.zeroize_and_close_required)
        self.assertFalse(contract.real_provider_bound)
        self.assertEqual(
            (contract.real_environment_read_budget, contract.credential_manager_read_budget),
            (0, 0),
        )
        self.assertEqual(contract.external_calls, 0)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_next_called)
        self.assertFalse(contract.bitrix_written)

    def test_module_has_no_real_source_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_owned_buffer_provisioning.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "getenv",
            "ctypes",
            "windll",
            "credread",
            "dotenv",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


def _zeroize_for_test(buffers):
    for value in buffers.values():
        value[:] = b"\x00" * len(value)
    buffers.clear()


if __name__ == "__main__":
    unittest.main()
