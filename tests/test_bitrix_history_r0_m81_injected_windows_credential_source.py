import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
    MAX_INJECTED_CREDENTIAL_TOTAL_BYTES,
    MAX_INJECTED_CREDENTIAL_VALUE_BYTES,
    WindowsCredentialProtectedValueSource,
    execute_injected_windows_credential_helper_once,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers(value_size=8):
    return {
        name: bytearray((f"fixture-{index}-" + "x" * value_size).encode())
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


class MemoryCredentialBackend:
    def __init__(self, *, record=None, error=None, close_error=None):
        self.record = record or InjectedWindowsCredentialRecord(
            target_id=M80_CREDENTIAL_TARGET_ID,
            buffers=fixture_buffers(),
        )
        self.error = error
        self.close_error = close_error
        self.fetch_calls = 0
        self.close_calls = 0
        self.targets = []

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        self.targets.append(target_id)
        if self.error is not None:
            raise self.error
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()
        if self.close_error is not None:
            raise self.close_error


class M81InjectedWindowsCredentialSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_record_composes_with_existing_helper_once(self):
        original = fixture_buffers()
        backend = MemoryCredentialBackend(
            record=InjectedWindowsCredentialRecord(
                target_id=M80_CREDENTIAL_TARGET_ID,
                buffers=original,
            )
        )
        operation_calls = 0

        async def operation(values):
            nonlocal operation_calls
            operation_calls += 1
            for name in PROTECTED_SETTING_NAMES:
                self.assertTrue(values.read_text(name).startswith("fixture-"))

        result = await execute_injected_windows_credential_helper_once(
            backend=backend,
            operation=operation,
        )

        self.assertEqual(result.state, ProtectedHelperState.READY)
        self.assertEqual(result.failure_category, "none")
        self.assertEqual((result.source_read_calls, result.operation_calls), (7, 1))
        self.assertTrue(result.resources_closed)
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))
        self.assertEqual(backend.targets, [M80_CREDENTIAL_TARGET_ID])
        self.assertEqual(operation_calls, 1)
        self.assertTrue(all(not any(value) for value in original.values()))

    async def test_target_mismatch_fails_closed_and_zeroizes(self):
        original = fixture_buffers()
        backend = MemoryCredentialBackend(
            record=InjectedWindowsCredentialRecord(
                target_id="wrong-target",
                buffers=original,
            )
        )
        calls = 0

        async def operation(_):
            nonlocal calls
            calls += 1

        result = await execute_injected_windows_credential_helper_once(
            backend=backend, operation=operation
        )

        self.assertEqual(result.state, ProtectedHelperState.NO_GO)
        self.assertEqual(
            result.failure_category,
            "protected_source_contract_invalid",
        )
        self.assertEqual(calls, 0)
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))
        self.assertTrue(all(not any(value) for value in original.values()))

    async def test_missing_or_extra_name_never_reaches_operation(self):
        for mutate in ("missing", "extra"):
            with self.subTest(mutate=mutate):
                buffers = fixture_buffers()
                if mutate == "missing":
                    buffers.pop(PROTECTED_SETTING_NAMES[-1])
                else:
                    buffers["NOT_ALLOWED"] = bytearray(b"fixture")
                backend = MemoryCredentialBackend(
                    record=InjectedWindowsCredentialRecord(
                        target_id=M80_CREDENTIAL_TARGET_ID,
                        buffers=buffers,
                    )
                )
                calls = 0

                async def operation(_):
                    nonlocal calls
                    calls += 1

                result = await execute_injected_windows_credential_helper_once(
                    backend=backend, operation=operation
                )
                self.assertEqual(result.state, ProtectedHelperState.NO_GO)
                self.assertEqual(
                    result.failure_category,
                    "protected_source_contract_invalid",
                )
                self.assertEqual(calls, 0)
                self.assertTrue(all(not any(value) for value in buffers.values()))

    async def test_foreign_record_or_buffer_container_fails_and_still_closes(self):
        variants = (
            object(),
            InjectedWindowsCredentialRecord(
                target_id=M80_CREDENTIAL_TARGET_ID,
                buffers=[],
            ),
        )
        for record in variants:
            with self.subTest(record_type=type(record).__name__):
                backend = MemoryCredentialBackend(record=record)
                calls = 0

                async def operation(_):
                    nonlocal calls
                    calls += 1

                result = await execute_injected_windows_credential_helper_once(
                    backend=backend, operation=operation
                )
                self.assertEqual(result.state, ProtectedHelperState.NO_GO)
                self.assertEqual(
                    result.failure_category,
                    "protected_source_contract_invalid",
                )
                self.assertEqual(calls, 0)
                self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))

    async def test_invalid_or_oversized_value_fails_closed(self):
        variants = []
        empty = fixture_buffers()
        empty[PROTECTED_SETTING_NAMES[0]] = bytearray()
        variants.append(empty)
        nul = fixture_buffers()
        nul[PROTECTED_SETTING_NAMES[0]] = bytearray(b"bad\x00value")
        variants.append(nul)
        oversized = fixture_buffers()
        oversized[PROTECTED_SETTING_NAMES[0]] = bytearray(
            b"x" * (MAX_INJECTED_CREDENTIAL_VALUE_BYTES + 1)
        )
        variants.append(oversized)
        total = {
            name: bytearray(b"x" * (MAX_INJECTED_CREDENTIAL_TOTAL_BYTES // 7 + 1))
            for name in PROTECTED_SETTING_NAMES
        }
        variants.append(total)
        for buffers in variants:
            with self.subTest(size=sum(len(value) for value in buffers.values())):
                backend = MemoryCredentialBackend(
                    record=InjectedWindowsCredentialRecord(
                        target_id=M80_CREDENTIAL_TARGET_ID,
                        buffers=buffers,
                    )
                )
                result = await execute_injected_windows_credential_helper_once(
                    backend=backend, operation=lambda _: None
                )
                self.assertEqual(result.state, ProtectedHelperState.NO_GO)
                self.assertEqual(
                    result.failure_category,
                    "protected_source_contract_invalid",
                )
                self.assertTrue(all(not any(value) for value in buffers.values()))

    async def test_backend_failure_closes_without_operation(self):
        backend = MemoryCredentialBackend(error=RuntimeError("fixture-failure"))
        calls = 0

        async def operation(_):
            nonlocal calls
            calls += 1

        result = await execute_injected_windows_credential_helper_once(
            backend=backend, operation=operation
        )

        self.assertEqual(result.state, ProtectedHelperState.NO_GO)
        self.assertEqual(result.failure_category, "protected_source_open_failed")
        self.assertEqual(calls, 0)
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))

    async def test_fetch_cancellation_is_terminal_and_closed(self):
        backend = MemoryCredentialBackend(error=asyncio.CancelledError())

        result = await execute_injected_windows_credential_helper_once(
            backend=backend, operation=lambda _: None
        )

        self.assertEqual(result.state, ProtectedHelperState.CANCELLED)
        self.assertTrue(result.resources_closed)
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))

    async def test_operation_cancellation_zeroizes_and_closes(self):
        original = fixture_buffers()
        backend = MemoryCredentialBackend(
            record=InjectedWindowsCredentialRecord(
                target_id=M80_CREDENTIAL_TARGET_ID,
                buffers=original,
            )
        )

        async def operation(_):
            raise asyncio.CancelledError()

        result = await execute_injected_windows_credential_helper_once(
            backend=backend, operation=operation
        )

        self.assertEqual(result.state, ProtectedHelperState.CANCELLED)
        self.assertTrue(result.resources_closed)
        self.assertEqual(backend.close_calls, 1)
        self.assertTrue(all(not any(value) for value in original.values()))

    async def test_close_failure_overrides_success_with_no_go(self):
        backend = MemoryCredentialBackend(close_error=RuntimeError("fixture-close"))

        async def operation(_):
            return None

        result = await execute_injected_windows_credential_helper_once(
            backend=backend, operation=operation
        )

        self.assertEqual(result.state, ProtectedHelperState.NO_GO)
        self.assertEqual(result.reason, "protected_helper_close_failed")
        self.assertFalse(result.resources_closed)
        self.assertEqual(backend.close_calls, 1)

    async def test_source_reuse_and_read_after_close_are_blocked(self):
        backend = MemoryCredentialBackend()
        source = WindowsCredentialProtectedValueSource(backend=backend)
        await source.open()
        await source.close()

        with self.assertRaises(RuntimeError):
            await source.open()
        with self.assertRaises(RuntimeError):
            await source.read(PROTECTED_SETTING_NAMES[0])
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))

    def test_repr_and_source_are_redacted_and_have_no_real_backend_or_fallback(self):
        backend = MemoryCredentialBackend()
        source = WindowsCredentialProtectedValueSource(backend=backend)
        self.assertEqual(repr(source), "WindowsCredentialProtectedValueSource(<redacted>)")
        self.assertEqual(repr(backend.record), "InjectedWindowsCredentialRecord(<redacted>)")
        module_source = (ROOT / "bitrix_connector" / "bitrix_history_r0_m81_injected_windows_credential_source.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "win32cred", "keyring", "ctypes", "credread", "credenumerate",
            "httpx", "pymongo", "dotenv", "os.environ", "argparse", "input(",
            "subprocess", "socket", "print(", "toast", "messagebox",
        ):
            self.assertNotIn(forbidden, module_source)


if __name__ == "__main__":
    unittest.main()
