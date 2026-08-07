import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    execute_injected_windows_credential_helper_once,
)
from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    CtypesWindowsGenericCredentialReader,
    M84_BLOB_MAGIC,
    WindowsCredentialManagerBackend,
    build_real_windows_credential_backend,
    inspect_m84_backend_contract,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_values():
    return {
        name: bytearray(f"fixture-m84-{index}".encode())
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


def fixture_blob(*, values=None, names=None, trailing=b""):
    values = values or fixture_values()
    names = names or PROTECTED_SETTING_NAMES
    blob = bytearray(M84_BLOB_MAGIC)
    for name in names:
        encoded_name = name.encode("ascii")
        value = values[name]
        blob.extend(len(encoded_name).to_bytes(2, "big"))
        blob.extend(encoded_name)
        blob.extend(len(value).to_bytes(4, "big"))
        blob.extend(value)
    blob.extend(trailing)
    return blob


class NativeFixture:
    def __init__(self, *, blob=None, error=None, close_error=None):
        self.blob = blob if blob is not None else fixture_blob()
        self.error = error
        self.close_error = close_error
        self.read_calls = 0
        self.close_calls = 0
        self.targets = []

    async def read_generic_blob_once(self, target_id):
        self.read_calls += 1
        self.targets.append(target_id)
        if self.error is not None:
            raise self.error
        blob, self.blob = self.blob, bytearray()
        return blob

    async def close(self):
        self.close_calls += 1
        if type(self.blob) is bytearray:
            self.blob[:] = b"\x00" * len(self.blob)
        if self.close_error is not None:
            raise self.close_error


class UnsafeNative(NativeFixture):
    async def enumerate_credentials(self):
        return []


class MissingCredentialApi:
    @staticmethod
    def CredReadW(*_args):
        return 0

    @staticmethod
    def CredFree(_pointer):
        return None


class M84WindowsCredentialBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_binary_record_composes_with_m81_without_real_access(self):
        original = fixture_blob()
        native = NativeFixture(blob=original)
        backend = WindowsCredentialManagerBackend(native=native)
        observed = []

        async def operation(view):
            observed.extend(view.read_text(name) for name in PROTECTED_SETTING_NAMES)

        result = await execute_injected_windows_credential_helper_once(
            backend=backend,
            operation=operation,
        )

        self.assertEqual(result.state, ProtectedHelperState.READY)
        self.assertEqual(result.failure_category, "none")
        self.assertEqual((result.source_read_calls, result.operation_calls), (7, 1))
        self.assertEqual((native.read_calls, native.close_calls), (1, 1))
        self.assertEqual(native.targets, [M80_CREDENTIAL_TARGET_ID])
        self.assertEqual(len(observed), 7)
        self.assertFalse(any(original))

    async def test_wrong_target_is_rejected_before_native_read(self):
        native = NativeFixture()
        backend = WindowsCredentialManagerBackend(native=native)

        with self.assertRaisesRegex(RuntimeError, "reuse_or_target_invalid"):
            await backend.fetch_exact("wrong-target")
        await backend.close()

        self.assertEqual((native.read_calls, native.close_calls), (0, 1))

    async def test_backend_is_one_shot_and_never_retries_native(self):
        native = NativeFixture(error=RuntimeError("private fixture"))
        backend = WindowsCredentialManagerBackend(native=native)

        with self.assertRaisesRegex(RuntimeError, "private fixture"):
            await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
        with self.assertRaisesRegex(RuntimeError, "reuse_or_target_invalid"):
            await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
        await backend.close()

        self.assertEqual((native.read_calls, native.close_calls), (1, 1))

    async def test_missing_extra_reordered_or_trailing_records_fail_closed(self):
        variants = (
            fixture_blob(names=PROTECTED_SETTING_NAMES[:-1]),
            fixture_blob(names=(*PROTECTED_SETTING_NAMES, PROTECTED_SETTING_NAMES[-1])),
            fixture_blob(names=(PROTECTED_SETTING_NAMES[1], PROTECTED_SETTING_NAMES[0], *PROTECTED_SETTING_NAMES[2:])),
            fixture_blob(trailing=b"x"),
        )
        for blob in variants:
            with self.subTest(size=len(blob)):
                native = NativeFixture(blob=blob)
                backend = WindowsCredentialManagerBackend(native=native)
                result = await execute_injected_windows_credential_helper_once(
                    backend=backend,
                    operation=lambda _view: None,
                )
                self.assertEqual(result.state, ProtectedHelperState.NO_GO)
                self.assertEqual(
                    result.failure_category,
                    "protected_source_blob_invalid",
                )
                self.assertEqual((native.read_calls, native.close_calls), (1, 1))
                self.assertFalse(any(blob))

    async def test_empty_nul_and_truncated_values_fail_and_zeroize_blob(self):
        empty_values = fixture_values()
        empty_values[PROTECTED_SETTING_NAMES[0]] = bytearray()
        nul_values = fixture_values()
        nul_values[PROTECTED_SETTING_NAMES[0]] = bytearray(b"bad\x00value")
        truncated = fixture_blob()[:-1]
        variants = (fixture_blob(values=empty_values), fixture_blob(values=nul_values), truncated)
        for blob in variants:
            with self.subTest(size=len(blob)):
                native = NativeFixture(blob=blob)
                backend = WindowsCredentialManagerBackend(native=native)
                result = await execute_injected_windows_credential_helper_once(
                    backend=backend,
                    operation=lambda _view: None,
                )
                self.assertEqual(result.state, ProtectedHelperState.NO_GO)
                self.assertEqual(
                    result.failure_category,
                    "protected_source_blob_invalid",
                )
                self.assertFalse(any(blob))

    async def test_api_unavailable_has_closed_public_category(self):
        reader = CtypesWindowsGenericCredentialReader()
        backend = WindowsCredentialManagerBackend(native=reader)

        with patch(
            "bitrix_connector.bitrix_history_r0_m84_windows_credential_backend.ctypes.WinDLL",
            side_effect=OSError("private-api-detail"),
        ):
            result = await execute_injected_windows_credential_helper_once(
                backend=backend,
                operation=lambda _view: None,
            )

        self.assertEqual(result.state, ProtectedHelperState.NO_GO)
        self.assertEqual(
            result.failure_category,
            "protected_source_api_unavailable",
        )
        self.assertNotIn("private-api-detail", repr(result))

    async def test_exact_record_unavailable_has_closed_public_category(self):
        reader = CtypesWindowsGenericCredentialReader()
        reader._api = MissingCredentialApi()
        backend = WindowsCredentialManagerBackend(native=reader)

        result = await execute_injected_windows_credential_helper_once(
            backend=backend,
            operation=lambda _view: None,
        )

        self.assertEqual(result.state, ProtectedHelperState.NO_GO)
        self.assertEqual(
            result.failure_category,
            "protected_source_record_unavailable",
        )

    async def test_cancellation_is_terminal_and_native_is_closed(self):
        native = NativeFixture(error=asyncio.CancelledError())
        backend = WindowsCredentialManagerBackend(native=native)

        result = await execute_injected_windows_credential_helper_once(
            backend=backend,
            operation=lambda _view: None,
        )

        self.assertEqual(result.state, ProtectedHelperState.CANCELLED)
        self.assertTrue(result.resources_closed)
        self.assertEqual((native.read_calls, native.close_calls), (1, 1))

    async def test_native_close_failure_remains_visible(self):
        native = NativeFixture(close_error=RuntimeError("private close"))
        backend = WindowsCredentialManagerBackend(native=native)

        result = await execute_injected_windows_credential_helper_once(
            backend=backend,
            operation=lambda _view: None,
        )

        self.assertEqual(result.state, ProtectedHelperState.NO_GO)
        self.assertEqual(result.reason, "protected_helper_close_failed")
        self.assertFalse(result.resources_closed)

    def test_unsafe_native_surface_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "surface_rejected"):
            WindowsCredentialManagerBackend(native=UnsafeNative())

    def test_real_factory_is_lazy_and_contract_reports_zero_real_reads(self):
        backend = build_real_windows_credential_backend()
        self.assertIsInstance(backend, WindowsCredentialManagerBackend)
        self.assertIsInstance(backend._native, CtypesWindowsGenericCredentialReader)
        self.assertIsNone(backend._native._api)

        snapshot = inspect_m84_backend_contract()
        self.assertEqual(snapshot.state, "IMPLEMENTED-NOT-READ")
        self.assertEqual(snapshot.real_credential_reads, 0)
        self.assertEqual(snapshot.max_blob_bytes, 2560)
        self.assertTrue(snapshot.native_blob_limit_verified)
        self.assertFalse(snapshot.credential_materializer_present)
        self.assertFalse(snapshot.credential_record_format_verified)
        self.assertEqual(snapshot.exact_read_budget, 1)
        self.assertEqual(
            (snapshot.enumeration_budget, snapshot.write_budget, snapshot.delete_budget),
            (0, 0, 0),
        )
        self.assertFalse(snapshot.source_opened)
        self.assertFalse(snapshot.command_available)

    def test_repr_and_source_expose_no_values_fallback_or_mutation_surface(self):
        native = NativeFixture()
        backend = WindowsCredentialManagerBackend(native=native)
        self.assertEqual(repr(backend), "WindowsCredentialManagerBackend(<redacted>)")
        self.assertEqual(
            repr(CtypesWindowsGenericCredentialReader()),
            "CtypesWindowsGenericCredentialReader(<redacted>)",
        )
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m84_windows_credential_backend.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "credenumeratew",
            "credwritew",
            "creddeletew",
            "keyring",
            "win32cred",
            "dotenv",
            "os.environ",
            "httpx",
            "pymongo",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "toast",
            "messagebox",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
