import json
import unittest
from pathlib import Path

from scripts.r1_key_vault_host_probe_payload import (
    EXPECTED_DISTRIBUTIONS,
    SCHEMA,
    SETTING_NAME,
    collect_sanitized,
)


ROOT = Path(__file__).resolve().parents[1]
EXACT_URL = "https://nia-next-r1-kv-260810.vault.azure.net"
VERSIONS = dict(EXPECTED_DISTRIBUTIONS)


class NoIterationMapping(dict):
    def __iter__(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def keys(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def items(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def values(self):
        raise AssertionError("environment_must_not_be_enumerated")


class R1KeyVaultHostProbePayloadTests(unittest.TestCase):
    def collect(self, environment):
        calls = []

        def version_reader(name):
            calls.append(name)
            return VERSIONS[name]

        return collect_sanitized(
            environ=NoIterationMapping(environment),
            version_reader=version_reader,
        ), calls

    def test_absent_setting_and_exact_versions_are_sanitized(self):
        result, calls = self.collect({})

        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["packages"], VERSIONS)
        self.assertFalse(result["setting_present"])
        self.assertIsNone(result["setting_valid"])
        self.assertEqual(calls, list(VERSIONS))

    def test_present_setting_is_validated_but_value_is_not_returned(self):
        result, _ = self.collect({SETTING_NAME: EXACT_URL})
        serialized = json.dumps(result)

        self.assertTrue(result["setting_present"])
        self.assertTrue(result["setting_valid"])
        self.assertNotIn(EXACT_URL, serialized)
        self.assertNotIn(SETTING_NAME, serialized)

    def test_noncanonical_setting_fails_closed(self):
        for value in ("", "http://wrong.vault.azure.net", EXACT_URL + "/"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "setting_invalid"):
                    self.collect({SETTING_NAME: value})

    def test_version_mismatch_fails_closed(self):
        versions = dict(VERSIONS)
        versions["azure-identity"] = "0.0.0"

        with self.assertRaisesRegex(RuntimeError, "version_mismatch"):
            collect_sanitized(
                environ=NoIterationMapping(),
                version_reader=versions.__getitem__,
            )

    def test_missing_distribution_is_redacted(self):
        def missing(_name):
            raise LookupError("private package path")

        with self.assertRaisesRegex(RuntimeError, "package_unavailable") as caught:
            collect_sanitized(
                environ=NoIterationMapping(),
                version_reader=missing,
            )

        self.assertNotIn("private package path", str(caught.exception))

    def test_scope_and_output_are_fixed(self):
        result, _ = self.collect({})

        self.assertEqual(
            set(result),
            {
                "schema",
                "packages",
                "setting_present",
                "setting_valid",
                "external_calls",
                "writes",
            },
        )
        self.assertEqual(result["external_calls"], 0)
        self.assertEqual(result["writes"], 0)

    def test_payload_has_no_enumeration_network_or_persistence_surface(self):
        text = (
            ROOT / "scripts" / "r1_key_vault_host_probe_payload.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".items(",
            ".keys(",
            ".values(",
            "subprocess",
            "socket",
            "httpx",
            "requests",
            "pathlib",
            "open(",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
