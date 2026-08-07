import ctypes
import unittest
from unittest.mock import patch

from bitrix_connector.bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    M86AEWindowsEnvironmentBackend,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AU_AUTHORIZATION_LITERAL,
)
from bitrix_connector.bitrix_history_r0_m86_owned_buffer_provisioning import (
    M86AZInjectedOwnedBufferProvider,
    M86AZOwnedBufferProvisioningSource,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_real_owner import (
    M86AVStageSpecificRealOwner,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


class FixtureWindowsApi:
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


def fixture_source(values=None, captured=None):
    selected = values or {
        name: f"fixture-m86-av-{index}"
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }
    source = M86AEDormantWindowsEnvironmentSource(
        backend=M86AEWindowsEnvironmentBackend(
            get_environment_variable_w=FixtureWindowsApi(selected).get,
            wide_char_to_multi_byte=FixtureWindowsApi(selected).convert,
        )
    )
    if captured is not None:
        captured.append(source)
    return source


def provisioned_source(values=None, captured=None):
    selected = values or {
        name: bytearray(f"fixture-m86-ba-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }
    source = M86AZOwnedBufferProvisioningSource(
        provider=M86AZInjectedOwnedBufferProvider(buffers=selected)
    )
    if captured is not None:
        captured.append(source)
    return source


class M86AVStageSpecificRealOwnerTests(unittest.TestCase):
    def test_preview_and_wrong_literal_do_not_call_factory(self):
        calls = []
        owner = M86AVStageSpecificRealOwner(
            source_factory=lambda: calls.append("forbidden")
        )
        preview = owner.preview()
        self.assertEqual((preview.real_factory_called, calls), (False, []))
        result = owner.run_once(confirm_code="sp")
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertEqual(calls, [])

    def test_injected_authorization_validator_replaces_default_gate(self):
        calls = []
        owner = M86AVStageSpecificRealOwner(
            source_factory=lambda: calls.append("forbidden"),
            authorization_validator=lambda candidate: candidate == "fixture-exact",
        )
        result = owner.run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "authorization_invalid")
        self.assertEqual(calls, [])

    def test_factory_failure_has_specific_category(self):
        def broken_factory():
            raise RuntimeError("fixture-factory")

        result = M86AVStageSpecificRealOwner(
            source_factory=broken_factory
        ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "source_factory_unavailable")

    def test_open_failure_has_specific_category_and_closes(self):
        captured = []
        values = {
            name: f"fixture-{index}"
            for index, name in enumerate(PROTECTED_SETTING_NAMES[:-1])
        }
        result = M86AVStageSpecificRealOwner(
            source_factory=lambda: fixture_source(values, captured)
        ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "source_open_unavailable")
        self.assertTrue(captured[0].resources_closed)

    def test_transfer_failure_has_specific_category_and_closes(self):
        captured = []
        with patch.object(
            M86AEDormantWindowsEnvironmentSource,
            "take_buffers_once",
            side_effect=RuntimeError("fixture-transfer"),
        ):
            result = M86AVStageSpecificRealOwner(
                source_factory=lambda: fixture_source(captured=captured)
            ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "source_transfer_unavailable")
        self.assertTrue(captured[0].resources_closed)

    def test_candidate_and_composition_failures_remain_aggregate(self):
        target = (
            "bitrix_connector.bitrix_history_r0_m86_stage_specific_real_owner."
            "materialize_m84_blob_from_injected_buffers"
        )
        with patch(target, side_effect=ValueError("fixture-fit")):
            fit = M86AVStageSpecificRealOwner(
                source_factory=fixture_source
            ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        with patch(target, side_effect=RuntimeError("fixture-composition")):
            composition = M86AVStageSpecificRealOwner(
                source_factory=fixture_source
            ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(fit.failure_category, "candidate_not_fit")
        self.assertEqual(composition.failure_category, "composition_failed")

    def test_exact_literal_with_fixture_returns_fit(self):
        result = M86AVStageSpecificRealOwner(
            source_factory=fixture_source
        ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))

    def test_cleanup_failure_overrides_fit(self):
        with patch.object(
            M86AEDormantWindowsEnvironmentSource,
            "close",
            side_effect=RuntimeError("fixture-cleanup"),
        ):
            result = M86AVStageSpecificRealOwner(
                source_factory=fixture_source
            ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "cleanup_ambiguous")

    def test_provisioned_buffer_source_returns_fit(self):
        result = M86AVStageSpecificRealOwner(
            source_factory=provisioned_source
        ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual((result.state, result.failure_category), ("FIT", "none"))

    def test_invalid_provisioned_aggregate_is_source_open_unavailable(self):
        values = {
            name: bytearray(f"fixture-{index}".encode("ascii"))
            for index, name in enumerate(PROTECTED_SETTING_NAMES[:-1])
        }
        captured = []
        result = M86AVStageSpecificRealOwner(
            source_factory=lambda: provisioned_source(values, captured)
        ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "source_open_unavailable")
        self.assertTrue(captured[0].resources_closed)

    def test_provisioned_source_cleanup_failure_overrides_fit(self):
        with patch.object(
            M86AZOwnedBufferProvisioningSource,
            "close",
            side_effect=RuntimeError("fixture-cleanup"),
        ):
            result = M86AVStageSpecificRealOwner(
                source_factory=provisioned_source
            ).run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "cleanup_ambiguous")

    def test_owner_is_one_shot_and_has_no_cli(self):
        owner = M86AVStageSpecificRealOwner(source_factory=fixture_source)
        owner.run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        with self.assertRaisesRegex(RuntimeError, "already_used"):
            owner.run_once(confirm_code=M86AU_AUTHORIZATION_LITERAL)
        self.assertFalse(hasattr(owner, "main"))


if __name__ == "__main__":
    unittest.main()
