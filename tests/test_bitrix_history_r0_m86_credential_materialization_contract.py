import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_FORMAT,
    M84_BLOB_MAGIC,
    MAX_M84_BLOB_BYTES,
    _parse_exact_blob,
)
from bitrix_connector.bitrix_history_r0_m86_credential_materialization_contract import (
    inspect_m86_credential_materialization_contract,
    materialize_m84_blob_from_injected_buffers,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-u-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


def zeroize(buffers):
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)


class M86CredentialMaterializationContractTests(unittest.TestCase):
    def test_fixture_roundtrip_matches_existing_m84_parser(self):
        buffers = fixture_buffers()
        expected = {name: bytes(value) for name, value in buffers.items()}
        owner = materialize_m84_blob_from_injected_buffers(buffers)
        blob = owner.take_blob_once()
        parsed = {}
        try:
            self.assertEqual(bytes(blob[: len(M84_BLOB_MAGIC)]), M84_BLOB_MAGIC)
            parsed = _parse_exact_blob(blob)
            self.assertEqual(
                {name: bytes(value) for name, value in parsed.items()},
                expected,
            )
            self.assertEqual(
                {name: bytes(value) for name, value in buffers.items()},
                expected,
            )
        finally:
            blob[:] = b"\x00" * len(blob)
            for value in parsed.values():
                value[:] = b"\x00" * len(value)
            owner.close()
            zeroize(buffers)
        self.assertFalse(any(blob))

    def test_owner_is_redacted_one_shot_and_clears_retained_blob(self):
        buffers = fixture_buffers()
        owner = materialize_m84_blob_from_injected_buffers(buffers)
        retained = owner._blob
        self.assertEqual(repr(owner), "M84MaterializedBlobOwner(<redacted>)")
        owner.close()
        self.assertFalse(any(retained))
        with self.assertRaisesRegex(RuntimeError, "blob_unavailable"):
            owner.take_blob_once()
        zeroize(buffers)

    def test_missing_extra_reordered_and_non_bytearray_fail_closed(self):
        variants = []
        missing = fixture_buffers()
        missing.pop(PROTECTED_SETTING_NAMES[-1])
        variants.append(missing)
        extra = fixture_buffers()
        extra["EXTRA"] = bytearray(b"fixture")
        variants.append(extra)
        reordered = fixture_buffers()
        first = reordered.pop(PROTECTED_SETTING_NAMES[0])
        reordered[PROTECTED_SETTING_NAMES[0]] = first
        variants.append(reordered)
        wrong_type = fixture_buffers()
        wrong_type[PROTECTED_SETTING_NAMES[0]] = b"fixture"
        variants.append(wrong_type)

        for buffers in variants:
            with self.subTest(keys=tuple(buffers)):
                with self.assertRaises(ValueError):
                    materialize_m84_blob_from_injected_buffers(buffers)
                zeroize(buffers)

    def test_empty_nul_oversize_and_aggregate_oversize_fail_closed(self):
        variants = []
        empty = fixture_buffers()
        empty[PROTECTED_SETTING_NAMES[0]] = bytearray()
        variants.append(empty)
        nul = fixture_buffers()
        nul[PROTECTED_SETTING_NAMES[0]] = bytearray(b"bad\x00fixture")
        variants.append(nul)
        oversized = fixture_buffers()
        oversized[PROTECTED_SETTING_NAMES[0]] = bytearray(b"x" * (8 * 1024 + 1))
        variants.append(oversized)
        aggregate = {
            name: bytearray(b"x" * 5000) for name in PROTECTED_SETTING_NAMES
        }
        variants.append(aggregate)

        for buffers in variants:
            with self.subTest(size=sum(len(value) for value in buffers.values())):
                with self.assertRaises(ValueError):
                    materialize_m84_blob_from_injected_buffers(buffers)
                zeroize(buffers)

    def test_exact_native_blob_limit_passes_and_one_extra_byte_fails(self):
        overhead = len(M84_BLOB_MAGIC) + sum(
            2 + len(name.encode("ascii")) + 4 for name in PROTECTED_SETTING_NAMES
        )
        payload_size = MAX_M84_BLOB_BYTES - overhead
        values = {name: bytearray(b"x") for name in PROTECTED_SETTING_NAMES}
        values[PROTECTED_SETTING_NAMES[0]].extend(
            b"x" * (payload_size - len(PROTECTED_SETTING_NAMES))
        )
        owner = materialize_m84_blob_from_injected_buffers(values)
        blob = owner.take_blob_once()
        try:
            self.assertEqual(len(blob), 2560)
        finally:
            blob[:] = b"\x00" * len(blob)
            owner.close()
        values[PROTECTED_SETTING_NAMES[0]].append(ord("x"))
        with self.assertRaisesRegex(ValueError, "blob_too_large"):
            materialize_m84_blob_from_injected_buffers(values)
        zeroize(values)

    def test_contract_is_inert_and_defines_both_rollback_branches(self):
        contract = inspect_m86_credential_materialization_contract()
        self.assertEqual((contract.phase, contract.state), ("M86-U", "PREPARED-INERT"))
        self.assertEqual(contract.target_id, M80_CREDENTIAL_TARGET_ID)
        self.assertEqual(contract.blob_format, M84_BLOB_FORMAT)
        self.assertTrue(contract.serializer_present)
        self.assertFalse(contract.real_value_source_bound)
        self.assertFalse(contract.operating_system_writer_present)
        self.assertFalse(contract.operating_system_delete_present)
        self.assertEqual(
            (
                contract.preflight_read_budget,
                contract.credential_write_budget,
                contract.credential_delete_budget,
                contract.credential_enumeration_budget,
                contract.external_call_budget,
            ),
            (0, 0, 0, 0, 0),
        )
        self.assertTrue(contract.two_separate_confirmations_required)
        self.assertTrue(contract.exact_preflight_required)
        self.assertTrue(contract.ambiguous_prior_state_is_no_go)
        self.assertEqual(contract.rollback_if_prior_absent, "delete_only_new_exact_target")
        self.assertEqual(contract.rollback_if_prior_present, "restore_exact_protected_prior_blob")
        self.assertFalse(contract.rollback_implementation_present)
        self.assertFalse(contract.real_execution_authorized)
        self.assertTrue(contract.connector_locked_off)
        self.assertFalse(contract.persisted)
        self.assertFalse(contract.nia_next_called)
        self.assertFalse(contract.bitrix_written)

    def test_module_has_no_real_source_writer_delete_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_credential_materialization_contract.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "ctypes",
            "windll",
            "credwritew",
            "creddeletew",
            "credenumeratew",
            "credreadw",
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
