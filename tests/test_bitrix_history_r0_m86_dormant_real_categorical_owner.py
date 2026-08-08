import ctypes
import unittest

from bitrix_connector.bitrix_history_r0_m86_categorical_probe_authorization import (
    M86AO_AUTHORIZATION_LITERAL,
)
from bitrix_connector.bitrix_history_r0_m86_dormant_real_categorical_owner import (
    M86ANDormantRealCategoricalOwner,
)
from bitrix_connector.bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    M86AEWindowsEnvironmentBackend,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


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


def fake_source_factory(values=None, calls=None):
    selected = values or {
        name: f"fixture-m86-an-{index}" for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }

    def build():
        if calls is not None:
            calls.append("factory")
        api = FakeApi(selected)
        return M86AEDormantWindowsEnvironmentSource(
            backend=M86AEWindowsEnvironmentBackend(
                get_environment_variable_w=api.get,
                wide_char_to_multi_byte=api.convert,
            )
        )

    return build


class M86ANDormantRealCategoricalOwnerTests(unittest.TestCase):
    def test_preview_does_not_call_bound_factory(self):
        calls = []
        preview = M86ANDormantRealCategoricalOwner(
            source_factory=fake_source_factory(calls=calls)
        ).preview()
        self.assertEqual(preview.state, "DORMANT-WAITING-AUTHORIZATION")
        self.assertTrue(preview.real_factory_bound)
        self.assertFalse(preview.real_factory_called)
        self.assertEqual((preview.current_real_read_budget, calls), (0, []))

    def test_wrong_literal_does_not_call_factory(self):
        calls = []
        result = M86ANDormantRealCategoricalOwner(
            source_factory=fake_source_factory(calls=calls)
        ).run_once(confirm_code="sp")
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertEqual(calls, [])

    def test_exact_literal_with_fixture_returns_fit(self):
        result = M86ANDormantRealCategoricalOwner(
            source_factory=fake_source_factory()
        ).run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))

    def test_factory_and_source_failures_are_aggregate(self):
        def broken_factory():
            raise RuntimeError("fixture")

        factory_failed = M86ANDormantRealCategoricalOwner(
            source_factory=broken_factory
        ).run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        values = {
            name: f"fixture-{index}" for index, name in enumerate(PROTECTED_SETTING_NAMES[:-1])
        }
        source_failed = M86ANDormantRealCategoricalOwner(
            source_factory=fake_source_factory(values)
        ).run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        self.assertEqual(factory_failed.failure_category, "source_aggregate_unavailable")
        self.assertEqual(source_failed.failure_category, "source_aggregate_unavailable")

    def test_owner_is_one_shot(self):
        owner = M86ANDormantRealCategoricalOwner(source_factory=fake_source_factory())
        owner.run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        with self.assertRaisesRegex(RuntimeError, "already_used"):
            owner.run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)


if __name__ == "__main__":
    unittest.main()
