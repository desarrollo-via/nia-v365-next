import ctypes
import unittest
from unittest.mock import patch

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
from bitrix_connector.bitrix_history_r0_m86_source_aggregate_failure_audit import (
    M86ARSourceAggregateFailureAudit,
    SOURCE_AGGREGATE_STAGES,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


class FixtureWindowsApi:
    def __init__(self, *, available=True):
        self.available = available

    def get(self, name, target, size):
        if not self.available:
            return 0
        value = f"fixture-m86-ar-{PROTECTED_SETTING_NAMES.index(name)}"
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


def fixture_source(*, available=True):
    api = FixtureWindowsApi(available=available)
    return M86AEDormantWindowsEnvironmentSource(
        backend=M86AEWindowsEnvironmentBackend(
            get_environment_variable_w=api.get,
            wide_char_to_multi_byte=api.convert,
        )
    )


class M86ARSourceAggregateFailureAuditTests(unittest.TestCase):
    def test_audit_freezes_three_possible_stages_without_claiming_one(self):
        audit = M86ARSourceAggregateFailureAudit()
        self.assertEqual(audit.possible_internal_stages, SOURCE_AGGREGATE_STAGES)
        self.assertFalse(audit.exact_internal_stage_identified)
        self.assertFalse(audit.individual_key_identified)

    def test_factory_failure_remains_aggregate(self):
        def broken_factory():
            raise RuntimeError("fixture-factory")

        result = M86ANDormantRealCategoricalOwner(
            source_factory=broken_factory
        ).run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        self.assertEqual(
            (result.state, result.failure_category),
            ("NO-GO", "source_aggregate_unavailable"),
        )

    def test_open_failure_remains_aggregate_and_closes_source(self):
        source = fixture_source(available=False)
        result = M86ANDormantRealCategoricalOwner(
            source_factory=lambda: source
        ).run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "source_aggregate_unavailable")
        self.assertTrue(source.resources_closed)

    def test_transfer_failure_remains_aggregate_and_closes_source(self):
        source = fixture_source()
        with patch.object(
            M86AEDormantWindowsEnvironmentSource,
            "take_buffers_once",
            side_effect=RuntimeError("fixture-transfer"),
        ):
            result = M86ANDormantRealCategoricalOwner(
                source_factory=lambda: source
            ).run_once(confirm_code=M86AO_AUTHORIZATION_LITERAL)
        self.assertEqual(result.failure_category, "source_aggregate_unavailable")
        self.assertTrue(source.resources_closed)

    def test_audit_has_zero_real_budget_and_no_disclosure(self):
        audit = M86ARSourceAggregateFailureAudit()
        self.assertEqual((audit.new_real_read_budget, audit.external_calls), (0, 0))
        self.assertFalse(audit.real_probe_retried)
        self.assertFalse(audit.value_disclosed)


if __name__ == "__main__":
    unittest.main()
