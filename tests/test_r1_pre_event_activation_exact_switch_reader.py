import unittest
from pathlib import Path

from bitrix_connector.r1_pre_event_activation_exact_switch_reader import (
    ExactSwitchBaselineProbe,
    MappingExactSwitchValueSource,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES,
    SWITCH_ORDER,
)


ROOT = Path(__file__).resolve().parents[1]


class NoIterationMapping(dict):
    def __iter__(self):
        raise AssertionError("mapping_must_not_be_enumerated")

    def keys(self):
        raise AssertionError("mapping_must_not_be_enumerated")

    def items(self):
        raise AssertionError("mapping_must_not_be_enumerated")

    def values(self):
        raise AssertionError("mapping_must_not_be_enumerated")


class R1ExactSwitchReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_only_three_exact_names_in_frozen_order(self):
        mapping = NoIterationMapping(EXPECTED_BASELINE_VALUES)
        source = MappingExactSwitchValueSource(mapping)
        probe = ExactSwitchBaselineProbe(source=source)

        result = await probe.collect(names=SWITCH_ORDER)

        self.assertEqual(tuple(item.name for item in result), SWITCH_ORDER)
        self.assertEqual(source.exact_reads, SWITCH_ORDER)
        self.assertTrue(all(item.present for item in result))

    async def test_absence_is_preserved_without_default_invention(self):
        source = MappingExactSwitchValueSource(NoIterationMapping())
        result = await ExactSwitchBaselineProbe(source=source).collect(
            names=SWITCH_ORDER
        )

        self.assertTrue(all(not item.present for item in result))
        self.assertTrue(all(item.value is None for item in result))

    async def test_mixed_presence_is_literal_and_reversible(self):
        mapping = NoIterationMapping(
            {SWITCH_ORDER[1]: EXPECTED_BASELINE_VALUES[SWITCH_ORDER[1]]}
        )
        result = await ExactSwitchBaselineProbe(
            source=MappingExactSwitchValueSource(mapping)
        ).collect(names=SWITCH_ORDER)

        self.assertFalse(result[0].present)
        self.assertTrue(result[1].present)
        self.assertFalse(result[2].present)

    async def test_wrong_scope_fails_before_any_lookup(self):
        source = MappingExactSwitchValueSource(
            NoIterationMapping(EXPECTED_BASELINE_VALUES)
        )
        probe = ExactSwitchBaselineProbe(source=source)

        with self.assertRaisesRegex(RuntimeError, "scope_invalid"):
            await probe.collect(names=tuple(reversed(SWITCH_ORDER)))

        self.assertEqual(source.exact_reads, ())

    async def test_unexpected_value_fails_closed_and_closes(self):
        mapping = NoIterationMapping(EXPECTED_BASELINE_VALUES)
        mapping[SWITCH_ORDER[2]] = "pre-event"
        source = MappingExactSwitchValueSource(mapping)

        with self.assertRaisesRegex(ValueError, "baseline_invalid"):
            await ExactSwitchBaselineProbe(source=source).collect(
                names=SWITCH_ORDER
            )

        with self.assertRaisesRegex(RuntimeError, "read_blocked"):
            source.read_exact_once(SWITCH_ORDER[0])

    async def test_probe_and_each_name_are_one_shot(self):
        source = MappingExactSwitchValueSource(
            NoIterationMapping(EXPECTED_BASELINE_VALUES)
        )
        probe = ExactSwitchBaselineProbe(source=source)
        await probe.collect(names=SWITCH_ORDER)

        with self.assertRaisesRegex(RuntimeError, "reuse_or_scope_invalid"):
            await probe.collect(names=SWITCH_ORDER)

    def test_source_contains_no_environment_binding_or_enumeration(self):
        text = (
            ROOT
            / "bitrix_connector"
            / "r1_pre_event_activation_exact_switch_reader.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            ".items(",
            ".keys(",
            ".values(",
            "list(mapping",
            "dict(mapping",
            "subprocess",
            "httpx",
            "requests",
            "print(",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
