import contextlib
import io
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_dotenv_source import (
    MAX_PROTECTED_DOTENV_BYTES,
    AllowlistedDotenvSource,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
    execute_protected_helper_once,
)


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_VALUES = {
    "NIA_BITRIX_DOMAIN": "fictional.example.invalid",
    "NIA_BITRIX_MEMBER_ID": "fictional-member",
    "NIA_BITRIX_CLIENT_ID": "fictional-client",
    "NIA_BITRIX_CLIENT_SECRET": "fictional=client#secret",
    "NIA_BITRIX_MONGO_URI": "fictional-mongo-uri",
    "NIA_BITRIX_MONGO_DB": "fictional-db",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION": "fictional-installations",
}


def fixture_payload(*, omit: str | None = None) -> bytes:
    lines = [
        b"# fixture M2 sin credenciales reales",
        b"IGNORED_SETTING=ignored-fictional-value",
    ]
    for position, name in enumerate(PROTECTED_SETTING_NAMES):
        if name == omit:
            continue
        value = FICTIONAL_VALUES[name]
        if position == 1:
            rendered = f"{name}='{value}'"
        elif position == 2:
            rendered = f'export {name}="{value}"'
        else:
            rendered = f"{name}={value}"
        lines.append(rendered.encode("utf-8"))
    return b"\n".join(lines) + b"\n"


class ProtectedDotenvSourceTests(unittest.IsolatedAsyncioTestCase):
    async def _execute_payload(self, payload: bytes, operation):
        with tempfile.TemporaryDirectory(prefix="nia-next-r0-m2-") as directory:
            fixture_path = Path(directory) / "protected-fixture.env"
            fixture_path.write_bytes(payload)
            source = AllowlistedDotenvSource(fixture_path)
            snapshot = await execute_protected_helper_once(
                source=source,
                operation=operation,
            )
            return snapshot, source, str(fixture_path)

    async def test_fixture_file_reads_only_allowlist_and_removes_quotes(self):
        observed = {}

        async def operation(values):
            for name in PROTECTED_SETTING_NAMES:
                observed[name] = values.read_text(name)

        snapshot, source, fixture_path = await self._execute_payload(
            fixture_payload(),
            operation,
        )

        self.assertEqual(snapshot.state, ProtectedHelperState.READY)
        self.assertEqual(snapshot.source_read_calls, 7)
        self.assertTrue(snapshot.required_values_present)
        self.assertTrue(snapshot.operation_completed)
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(observed, FICTIONAL_VALUES)
        self.assertEqual(repr(source), "AllowlistedDotenvSource(<redacted>)")
        self.assertNotIn(fixture_path, repr(source))

    async def test_missing_or_duplicate_name_fails_without_position_signal(self):
        operation_calls = 0

        async def operation(_values):
            nonlocal operation_calls
            operation_calls += 1

        missing, _source, _path = await self._execute_payload(
            fixture_payload(omit=PROTECTED_SETTING_NAMES[2]),
            operation,
        )
        duplicate_payload = fixture_payload() + (
            f"{PROTECTED_SETTING_NAMES[0]}=fictional-duplicate\n".encode("utf-8")
        )
        duplicate, _source, _path = await self._execute_payload(
            duplicate_payload,
            operation,
        )

        for snapshot in (missing, duplicate):
            self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
            self.assertEqual(snapshot.reason, "protected_helper_failed_safe")
            self.assertEqual(snapshot.source_read_calls, 0)
            self.assertEqual(snapshot.operation_calls, 0)
            self.assertFalse(snapshot.required_values_present)
            self.assertTrue(snapshot.resources_closed)
        self.assertEqual(operation_calls, 0)

    async def test_malformed_quote_and_oversize_fail_closed(self):
        async def forbidden_operation(_values):
            self.fail("operation must not run")

        malformed = fixture_payload().replace(
            b"NIA_BITRIX_MEMBER_ID='fictional-member'",
            b"NIA_BITRIX_MEMBER_ID='fictional-member",
        )
        oversized = b"X=" + b"a" * MAX_PROTECTED_DOTENV_BYTES

        for payload in (malformed, oversized):
            with self.subTest(size=len(payload)):
                snapshot, _source, _path = await self._execute_payload(
                    payload,
                    forbidden_operation,
                )
                self.assertEqual(snapshot.state, ProtectedHelperState.NO_GO)
                self.assertEqual(snapshot.reason, "protected_helper_failed_safe")
                self.assertEqual(snapshot.source_read_calls, 0)
                self.assertTrue(snapshot.resources_closed)

    async def test_failures_never_emit_path_names_or_fictional_values(self):
        async def operation(_values):
            return None

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            snapshot, source, fixture_path = await self._execute_payload(
                fixture_payload(omit=PROTECTED_SETTING_NAMES[-1]),
                operation,
            )
        serialized = repr(asdict(snapshot)) + repr(source) + output.getvalue()
        self.assertNotIn(fixture_path, serialized)
        for name, value in FICTIONAL_VALUES.items():
            self.assertNotIn(name, serialized)
            self.assertNotIn(value, serialized)

    async def test_source_is_one_shot_and_symlinks_are_blocked_when_available(self):
        with tempfile.TemporaryDirectory(prefix="nia-next-r0-m2-") as directory:
            fixture_path = Path(directory) / "protected-fixture.env"
            fixture_path.write_bytes(fixture_payload())
            source = AllowlistedDotenvSource(fixture_path)
            await source.open()
            await source.close()
            with self.assertRaisesRegex(RuntimeError, "protected_dotenv_source_reused"):
                await source.open()

            link_path = Path(directory) / "protected-link.env"
            try:
                link_path.symlink_to(fixture_path)
            except OSError:
                return
            linked_source = AllowlistedDotenvSource(link_path)
            with self.assertRaisesRegex(ValueError, "protected_dotenv_symlink_blocked"):
                await linked_source.open()
            await linked_source.close()

    def test_adapter_has_no_environment_network_or_service_access(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_dotenv_source.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "os.environ",
            "load_dotenv",
            "keyring",
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


if __name__ == "__main__":
    unittest.main()
