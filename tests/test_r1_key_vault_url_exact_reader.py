import unittest
from pathlib import Path

from bitrix_connector.r1_key_vault_url_exact_reader import (
    ExactKeyVaultUrlBaselineProbe,
    KEY_VAULT_URL_SETTING_NAME,
    MappingExactKeyVaultUrlValueSource,
)


ROOT = Path(__file__).resolve().parents[1]
EXACT_URL = "https://nia-next-r1-kv-260810.vault.azure.net"


class NoIterationMapping(dict):
    def __iter__(self):
        raise AssertionError("mapping_must_not_be_enumerated")

    def keys(self):
        raise AssertionError("mapping_must_not_be_enumerated")

    def items(self):
        raise AssertionError("mapping_must_not_be_enumerated")

    def values(self):
        raise AssertionError("mapping_must_not_be_enumerated")


class R1KeyVaultUrlExactReaderTests(unittest.TestCase):
    def test_construction_is_dormant_until_exact_collect(self):
        source = MappingExactKeyVaultUrlValueSource(
            NoIterationMapping({KEY_VAULT_URL_SETTING_NAME: EXACT_URL})
        )
        probe = ExactKeyVaultUrlBaselineProbe(source=source)

        self.assertEqual(source.exact_reads, 0)
        result = probe.collect(name=KEY_VAULT_URL_SETTING_NAME)

        self.assertEqual(source.exact_reads, 1)
        self.assertTrue(result.present)
        self.assertEqual(result.value, EXACT_URL)

    def test_absence_is_preserved_without_default(self):
        result = ExactKeyVaultUrlBaselineProbe(
            source=MappingExactKeyVaultUrlValueSource(NoIterationMapping())
        ).collect(name=KEY_VAULT_URL_SETTING_NAME)

        self.assertFalse(result.present)
        self.assertIsNone(result.value)

    def test_wrong_scope_fails_before_mapping_read(self):
        source = MappingExactKeyVaultUrlValueSource(NoIterationMapping())
        probe = ExactKeyVaultUrlBaselineProbe(source=source)

        with self.assertRaisesRegex(RuntimeError, "scope_invalid"):
            probe.collect(name="WRONG_SETTING")

        self.assertEqual(source.exact_reads, 0)

    def test_source_is_one_shot(self):
        source = MappingExactKeyVaultUrlValueSource(
            NoIterationMapping({KEY_VAULT_URL_SETTING_NAME: EXACT_URL})
        )
        source.read_exact_once(KEY_VAULT_URL_SETTING_NAME)

        with self.assertRaisesRegex(RuntimeError, "read_blocked"):
            source.read_exact_once(KEY_VAULT_URL_SETTING_NAME)

    def test_probe_is_one_shot(self):
        probe = ExactKeyVaultUrlBaselineProbe(
            source=MappingExactKeyVaultUrlValueSource(NoIterationMapping())
        )
        probe.collect(name=KEY_VAULT_URL_SETTING_NAME)

        with self.assertRaisesRegex(RuntimeError, "reuse_or_scope_invalid"):
            probe.collect(name=KEY_VAULT_URL_SETTING_NAME)

    def test_invalid_or_noncanonical_url_fails_closed(self):
        for value in (
            "http://nia-next-r1-kv-260810.vault.azure.net",
            EXACT_URL + "/",
            "https://wrong.example.test",
            " HTTPS://nia-next-r1-kv-260810.vault.azure.net",
        ):
            with self.subTest(value=value):
                probe = ExactKeyVaultUrlBaselineProbe(
                    source=MappingExactKeyVaultUrlValueSource(
                        NoIterationMapping({KEY_VAULT_URL_SETTING_NAME: value})
                    )
                )
                with self.assertRaisesRegex(ValueError, "baseline_invalid"):
                    probe.collect(name=KEY_VAULT_URL_SETTING_NAME)

    def test_non_string_value_fails_closed(self):
        probe = ExactKeyVaultUrlBaselineProbe(
            source=MappingExactKeyVaultUrlValueSource(
                NoIterationMapping({KEY_VAULT_URL_SETTING_NAME: 42})
            )
        )

        with self.assertRaisesRegex(ValueError, "value_invalid"):
            probe.collect(name=KEY_VAULT_URL_SETTING_NAME)

    def test_source_has_no_enumeration_network_output_or_environment_default(self):
        text = (
            ROOT / "bitrix_connector" / "r1_key_vault_url_exact_reader.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            ".items(",
            ".keys(",
            ".values(",
            "subprocess",
            "httpx",
            "requests",
            "print(",
        ):
            self.assertNotIn(forbidden, text)

    def test_sdk_and_async_transport_are_exactly_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertEqual(requirements.count("azure-identity==1.25.3"), 1)
        self.assertEqual(requirements.count("azure-keyvault-secrets==4.11.0"), 1)
        self.assertEqual(requirements.count("aiohttp==3.14.3"), 1)


if __name__ == "__main__":
    unittest.main()
