import unittest
from pathlib import Path
from unittest.mock import patch

from bitrix_connector.r1_key_vault_protected_host_probe import (
    EXPECTED_DISTRIBUTIONS,
    SETTING_NAME,
)
from bitrix_connector.r1_key_vault_protected_host_probe_binding import (
    build_protected_host_probe,
)


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = dict(EXPECTED_DISTRIBUTIONS)
EXACT_URL = "https://nia-next-r1-kv-260810.vault.azure.net"


class ExactReadEnvironment(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reads = []

    def __getitem__(self, key):
        self.reads.append(key)
        return super().__getitem__(key)

    def __iter__(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def get(self, _key, _default=None):
        raise AssertionError("environment_must_use_direct_subscription")

    def keys(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def items(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def values(self):
        raise AssertionError("environment_must_not_be_enumerated")


class R1KeyVaultProtectedHostProbeBindingTests(unittest.TestCase):
    def test_build_is_dormant_then_reads_only_exact_allowlists(self):
        environment = ExactReadEnvironment({SETTING_NAME: EXACT_URL})
        package_reads = []

        def version(name):
            package_reads.append(name)
            return VERSIONS[name]

        with patch(
            "bitrix_connector.r1_key_vault_protected_host_probe_binding.os.environ",
            environment,
        ), patch(
            "bitrix_connector.r1_key_vault_protected_host_probe_binding.importlib.metadata.version",
            version,
        ):
            probe = build_protected_host_probe()
            self.assertEqual(environment.reads, [])
            self.assertEqual(package_reads, [])
            evidence = probe.collect_once()

        self.assertEqual(package_reads, list(VERSIONS))
        self.assertEqual(environment.reads, [SETTING_NAME])
        self.assertTrue(evidence.setting_present)
        self.assertTrue(evidence.setting_valid)
        self.assertNotIn(EXACT_URL, evidence.model_dump_json(by_alias=True))

    def test_absence_and_version_failure_are_sanitized_and_one_shot(self):
        environment = ExactReadEnvironment()

        with patch(
            "bitrix_connector.r1_key_vault_protected_host_probe_binding.os.environ",
            environment,
        ), patch(
            "bitrix_connector.r1_key_vault_protected_host_probe_binding.importlib.metadata.version",
            side_effect=lambda name: VERSIONS[name],
        ):
            probe = build_protected_host_probe()
            evidence = probe.collect_once()

        self.assertFalse(evidence.setting_present)
        self.assertIsNone(evidence.setting_valid)
        self.assertEqual(environment.reads, [SETTING_NAME])
        with self.assertRaisesRegex(RuntimeError, "already_consumed"):
            probe.collect_once()

        with patch(
            "bitrix_connector.r1_key_vault_protected_host_probe_binding.os.environ",
            ExactReadEnvironment(),
        ), patch(
            "bitrix_connector.r1_key_vault_protected_host_probe_binding.importlib.metadata.version",
            side_effect=RuntimeError("private package detail"),
        ):
            failed = build_protected_host_probe()
            with self.assertRaisesRegex(RuntimeError, "package_unavailable") as error:
                failed.collect_once()

        self.assertNotIn("private package detail", str(error.exception))
        with self.assertRaisesRegex(RuntimeError, "already_consumed"):
            failed.collect_once()

    def test_binding_has_no_collection_or_external_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "r1_key_vault_protected_host_probe_binding.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "collect_once(",
            ".get(",
            ".items(",
            ".keys(",
            ".values(",
            "subprocess",
            "socket",
            "httpx",
            "requests",
            "print(",
        ):
            self.assertNotIn(forbidden, source)

    def test_productive_router_injects_the_lazy_owner(self):
        source = (ROOT / "bitrix_connector" / "router.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("protected_host_probe = build_protected_host_probe()", source)
        self.assertIn("host_probe=protected_host_probe", source)


if __name__ == "__main__":
    unittest.main()
