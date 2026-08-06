import contextlib
import ctypes
import io
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    M86AEWindowsEnvironmentBackend,
)
from bitrix_connector.bitrix_history_r0_m86_environment_probe_authorization import (
    M86AF_AUTHORIZATION_LITERAL,
)
from bitrix_connector.bitrix_history_r0_m86_environment_probe_owner import (
    M86AIEnvironmentProbeOwner,
    main,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


ROOT = Path(__file__).resolve().parents[1]


class FakeApi:
    def __init__(self, values):
        self.values = values

    def get(self, name, target, size):
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


def source_factory(values=None):
    selected = values or {
        name: f"fixture-m86-ai-{index}" for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }

    def build():
        api = FakeApi(selected)
        return M86AEDormantWindowsEnvironmentSource(
            backend=M86AEWindowsEnvironmentBackend(
                get_environment_variable_w=api.get,
                wide_char_to_multi_byte=api.convert,
            )
        )

    return build


class M86AIEnvironmentProbeOwnerTests(unittest.TestCase):
    def test_exact_literal_returns_only_fit_with_fixture(self):
        result = M86AIEnvironmentProbeOwner().run_once(
            confirm_code=M86AF_AUTHORIZATION_LITERAL,
            source_factory=source_factory(),
        )
        self.assertEqual(result, "FIT")

    def test_wrong_literal_never_builds_source(self):
        calls = []
        result = M86AIEnvironmentProbeOwner().run_once(
            confirm_code="sp",
            source_factory=lambda: calls.append(True),
        )
        self.assertEqual(result, "NO-GO")
        self.assertEqual(calls, [])

    def test_missing_exact_value_is_aggregate_no_go(self):
        values = {
            name: f"fixture-{index}" for index, name in enumerate(PROTECTED_SETTING_NAMES[:-1])
        }
        result = M86AIEnvironmentProbeOwner().run_once(
            confirm_code=M86AF_AUTHORIZATION_LITERAL,
            source_factory=source_factory(values),
        )
        self.assertEqual(result, "NO-GO")

    def test_owner_is_one_shot(self):
        owner = M86AIEnvironmentProbeOwner()
        owner.run_once(
            confirm_code=M86AF_AUTHORIZATION_LITERAL,
            source_factory=source_factory(),
        )
        with self.assertRaisesRegex(RuntimeError, "already_used"):
            owner.run_once(
                confirm_code=M86AF_AUTHORIZATION_LITERAL,
                source_factory=source_factory(),
            )

    def test_cli_output_is_exactly_categorical(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                ["--confirm-code", M86AF_AUTHORIZATION_LITERAL],
                source_factory=source_factory(),
            )
        self.assertEqual((exit_code, output.getvalue()), (0, "FIT\n"))

    def test_invalid_cli_does_not_build_source(self):
        calls = []
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([], source_factory=lambda: calls.append(True))
        self.assertEqual((exit_code, output.getvalue(), calls), (1, "NO-GO\n", []))

    def test_module_has_no_forbidden_external_or_write_surface(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_m86_environment_probe_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "dotenv",
            "credwrite",
            "creddelete",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "requests",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
