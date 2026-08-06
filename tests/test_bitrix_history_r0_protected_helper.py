import asyncio
import contextlib
import io
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
    execute_protected_helper_once,
)
from bitrix_connector.bitrix_history_r0_protected_helper_cli import (
    PROTECTED_HELPER_FIXTURE_CONFIRMATION,
    main,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PREFIX = "fictional-r0-value"


class FakeProtectedSource:
    def __init__(
        self,
        *,
        missing_name: str | None = None,
        fail_on_open: bool = False,
        fail_on_read: bool = False,
        fail_on_close: bool = False,
    ) -> None:
        self.missing_name = missing_name
        self.fail_on_open = fail_on_open
        self.fail_on_read = fail_on_read
        self.fail_on_close = fail_on_close
        self.open_calls = 0
        self.read_names = []
        self.close_calls = 0
        self.transferred_buffers = []

    async def open(self) -> None:
        self.open_calls += 1
        if self.fail_on_open:
            raise RuntimeError("protected-open-detail")

    async def read(self, name: str) -> bytearray:
        self.read_names.append(name)
        if self.fail_on_read:
            raise RuntimeError(f"protected-detail-{name}")
        if name == self.missing_name:
            return bytearray()
        value = bytearray(f"{FIXTURE_PREFIX}-{name}", "utf-8")
        self.transferred_buffers.append(value)
        return value

    async def close(self) -> None:
        self.close_calls += 1
        if self.fail_on_close:
            raise RuntimeError("protected-close-detail")


class ProtectedHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_reads_exact_allowlist_once_and_zeroizes_buffers(self):
        source = FakeProtectedSource()
        operation_calls = []
        retained_view = []

        async def operation(values):
            retained_view.append(values)
            operation_calls.append(
                tuple(values.read_text(name).startswith(FIXTURE_PREFIX) for name in PROTECTED_SETTING_NAMES)
            )

        snapshot = await execute_protected_helper_once(
            source=source,
            operation=operation,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.READY)
        self.assertEqual(snapshot.reason, "protected_helper_completed")
        self.assertTrue(snapshot.protected_source_opened)
        self.assertTrue(snapshot.required_values_present)
        self.assertTrue(snapshot.operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.source_read_calls, 7)
        self.assertEqual(snapshot.operation_calls, 1)
        self.assertEqual(snapshot.failure_category, "none")
        self.assertEqual(source.open_calls, 1)
        self.assertEqual(tuple(source.read_names), PROTECTED_SETTING_NAMES)
        self.assertEqual(source.close_calls, 1)
        self.assertEqual(operation_calls, [(True,) * 7])
        self.assertTrue(source.transferred_buffers)
        self.assertTrue(
            all(not any(buffer) for buffer in source.transferred_buffers)
        )
        self.assertEqual(repr(retained_view[0]), "ProtectedValueView(<redacted>)")
        with self.assertRaisesRegex(RuntimeError, "protected_helper_view_closed"):
            retained_view[0].read_text(PROTECTED_SETTING_NAMES[0])

    async def test_missing_value_fails_closed_without_operation(self):
        source = FakeProtectedSource(missing_name=PROTECTED_SETTING_NAMES[3])
        operation_calls = 0

        async def operation(_values):
            nonlocal operation_calls
            operation_calls += 1

        snapshot = await execute_protected_helper_once(
            source=source,
            operation=operation,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(snapshot.reason, "protected_helper_failed_safe")
        self.assertTrue(snapshot.protected_source_opened)
        self.assertFalse(snapshot.required_values_present)
        self.assertFalse(snapshot.operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.operation_calls, 0)
        self.assertEqual(
            snapshot.failure_category,
            "protected_values_transfer_failed",
        )
        self.assertEqual(operation_calls, 0)
        self.assertEqual(source.close_calls, 1)
        self.assertTrue(
            all(not any(buffer) for buffer in source.transferred_buffers)
        )

    async def test_source_and_operation_failures_are_redacted(self):
        protected_details = [
            "protected-detail-NIA_BITRIX_DOMAIN",
            "protected-operation-detail",
        ]

        async def operation_failure(_values):
            raise RuntimeError(protected_details[1])

        cases = (
            (
                FakeProtectedSource(fail_on_open=True),
                lambda _values: asyncio.sleep(0),
                "protected_source_open_failed",
            ),
            (
                FakeProtectedSource(fail_on_read=True),
                lambda _values: asyncio.sleep(0),
                "protected_values_transfer_failed",
            ),
            (
                FakeProtectedSource(),
                operation_failure,
                "protected_operation_failed",
            ),
        )
        for source, operation, category in cases:
            with self.subTest(category=category):
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    snapshot = await execute_protected_helper_once(
                        source=source,
                        operation=operation,
                    )
                serialized = repr(asdict(snapshot)) + output.getvalue()
                self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
                self.assertEqual(snapshot.reason, "protected_helper_failed_safe")
                self.assertEqual(snapshot.failure_category, category)
                self.assertTrue(snapshot.resources_closed)
                for detail in protected_details:
                    self.assertNotIn(detail, serialized)
                self.assertNotIn(FIXTURE_PREFIX, serialized)

    async def test_close_failure_is_terminal_and_visible_without_detail(self):
        source = FakeProtectedSource(fail_on_close=True)

        async def operation(_values):
            return None

        snapshot = await execute_protected_helper_once(
            source=source,
            operation=operation,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
        self.assertEqual(snapshot.reason, "protected_helper_close_failed")
        self.assertTrue(snapshot.operation_completed)
        self.assertFalse(snapshot.resources_closed)
        self.assertEqual(
            snapshot.failure_category,
            "protected_resources_close_failed",
        )
        self.assertNotIn("protected-close-detail", repr(snapshot))
        self.assertTrue(
            all(not any(buffer) for buffer in source.transferred_buffers)
        )

    async def test_cancellation_returns_safe_state_after_cleanup(self):
        source = FakeProtectedSource()

        async def operation(_values):
            raise asyncio.CancelledError

        snapshot = await execute_protected_helper_once(
            source=source,
            operation=operation,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.CANCELLED)
        self.assertEqual(snapshot.reason, "protected_helper_cancelled")
        self.assertFalse(snapshot.operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.failure_category, "cancelled")
        self.assertTrue(
            all(not any(buffer) for buffer in source.transferred_buffers)
        )

    def test_source_has_no_real_secret_network_or_service_adapters(self):
        source = "\n".join(
            (
                (
                    ROOT
                    / "bitrix_connector"
                    / "bitrix_history_r0_protected_helper.py"
                ).read_text(encoding="utf-8"),
                (
                    ROOT
                    / "bitrix_connector"
                    / "bitrix_history_r0_protected_helper_cli.py"
                ).read_text(encoding="utf-8"),
            )
        )
        for forbidden in (
            "load_dotenv",
            "dotenv",
            "os.environ",
            "keyring",
            "CredentialManager",
            "httpx",
            "requests",
            "pymongo",
            "motor",
            "get_access_token",
            "refresh_access_token",
            "imopenlines",
            "subprocess",
            "socket",
        ):
            self.assertNotIn(forbidden, source)

    def test_fixture_cli_emits_only_aggregate_snapshot(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                ["--confirm-code", PROTECTED_HELPER_FIXTURE_CONFIRMATION]
            )

        raw = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('"state": "READY"', raw)
        self.assertIn('"resources_closed": true', raw)
        self.assertIn('"source_read_calls": 7', raw)
        self.assertNotIn("fictional-value", raw)
        for name in PROTECTED_SETTING_NAMES:
            self.assertNotIn(name, raw)

    def test_fixture_cli_rejects_any_other_confirmation(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["--confirm-code", "incorrecta"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
