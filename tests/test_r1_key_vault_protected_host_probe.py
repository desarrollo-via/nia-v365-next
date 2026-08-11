import json
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.config import load_settings
from bitrix_connector.r1_key_vault_protected_host_probe import (
    EXPECTED_DISTRIBUTIONS,
    SETTING_NAME,
    ExactOneShotProtectedHostProbe,
)
from bitrix_connector.review_router import create_review_router


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = dict(EXPECTED_DISTRIBUTIONS)
EXACT_URL = "https://nia-next-r1-kv-260810.vault.azure.net"


class NoIterationMapping(dict):
    def __iter__(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def keys(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def items(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def values(self):
        raise AssertionError("environment_must_not_be_enumerated")


class ProbeDouble:
    def __init__(self, owner=None, error=None):
        self.owner = owner
        self.error = error
        self.calls = 0

    def collect_once(self):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return self.owner.collect_once()


class UnreachableReviewReader:
    def __getattr__(self, _name):
        raise AssertionError("review_runtime_must_not_be_used")


def owner(environment=None, versions=None):
    values = dict(VERSIONS if versions is None else versions)
    return ExactOneShotProtectedHostProbe(
        environ=NoIterationMapping(environment or {}),
        version_reader=values.__getitem__,
    )


def client(probe):
    settings = load_settings(
        {
            "NIA_BITRIX_REVIEW_TOKEN": "review-token-that-is-long-enough",
            "NIA_BITRIX_REVIEW_ACTOR": "controlled-reviewer",
            "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "credential-v1",
        }
    )
    app = FastAPI()
    app.include_router(
        create_review_router(
            UnreachableReviewReader(),
            settings_loader=lambda: settings,
            include_decisions=False,
            host_probe=probe,
        ),
        prefix="/bitrix-connector",
    )
    return TestClient(app)


class R1KeyVaultProtectedHostProbeTests(unittest.TestCase):
    def test_owner_is_dormant_exact_and_one_shot_for_absence(self):
        calls = []

        def version_reader(name):
            calls.append(name)
            return VERSIONS[name]

        probe = ExactOneShotProtectedHostProbe(
            environ=NoIterationMapping(),
            version_reader=version_reader,
        )
        self.assertEqual(calls, [])

        evidence = probe.collect_once()

        self.assertEqual(calls, list(VERSIONS))
        self.assertFalse(evidence.setting_present)
        self.assertIsNone(evidence.setting_valid)
        with self.assertRaisesRegex(RuntimeError, "already_consumed"):
            probe.collect_once()

    def test_present_value_is_validated_but_never_returned(self):
        evidence = owner({SETTING_NAME: EXACT_URL}).collect_once()
        serialized = evidence.model_dump_json(by_alias=True)

        self.assertTrue(evidence.setting_present)
        self.assertTrue(evidence.setting_valid)
        self.assertNotIn(EXACT_URL, serialized)
        self.assertNotIn(SETTING_NAME, serialized)

    def test_version_or_setting_drift_fails_closed_and_consumes(self):
        versions = dict(VERSIONS)
        versions["azure-identity"] = "0.0.0"
        probes = (
            owner(versions=versions),
            owner({SETTING_NAME: EXACT_URL + "/"}),
        )
        for probe in probes:
            with self.subTest(probe=probe):
                with self.assertRaises(RuntimeError):
                    probe.collect_once()
                with self.assertRaisesRegex(RuntimeError, "already_consumed"):
                    probe.collect_once()

    def test_unauthorized_request_does_not_consume_owner(self):
        probe = ProbeDouble(owner())
        with client(probe) as http:
            denied = http.get("/bitrix-connector/review/r1-key-vault-host-probe")
            accepted = http.get(
                "/bitrix-connector/review/r1-key-vault-host-probe",
                headers={"Authorization": "Bearer review-token-that-is-long-enough"},
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(probe.calls, 1)
        self.assertEqual(accepted.status_code, 200)

    def test_authorized_route_returns_only_sanitized_schema(self):
        with client(ProbeDouble(owner())) as http:
            response = http.get(
                "/bitrix-connector/review/r1-key-vault-host-probe",
                headers={"Authorization": "Bearer review-token-that-is-long-enough"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "schema": "nia-next-r1-host-probe-v1",
                "packages": VERSIONS,
                "setting_present": False,
                "setting_valid": None,
                "external_calls": 0,
                "writes": 0,
            },
        )

    def test_fixed_route_is_not_captured_as_event_key_and_is_one_shot(self):
        probe = ProbeDouble(owner())
        headers = {"Authorization": "Bearer review-token-that-is-long-enough"}
        with client(probe) as http:
            first = http.get(
                "/bitrix-connector/review/r1-key-vault-host-probe",
                headers=headers,
            )
            second = http.get(
                "/bitrix-connector/review/r1-key-vault-host-probe",
                headers=headers,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], "host_probe_already_consumed")

    def test_unbound_or_failed_probe_is_sanitized(self):
        headers = {"Authorization": "Bearer review-token-that-is-long-enough"}
        for probe, expected in (
            (None, "host_probe_not_bound"),
            (ProbeDouble(error="private package path"), "host_probe_evidence_unavailable"),
        ):
            with self.subTest(probe=probe):
                with client(probe) as http:
                    response = http.get(
                        "/bitrix-connector/review/r1-key-vault-host-probe",
                        headers=headers,
                    )
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["detail"], expected)
                self.assertNotIn("private package path", response.text)

    def test_module_has_no_environment_import_network_or_output_surface(self):
        text = (
            ROOT / "bitrix_connector" / "r1_key_vault_protected_host_probe.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "importlib.metadata",
            ".items(",
            ".keys(",
            ".values(",
            "subprocess",
            "socket",
            "httpx",
            "requests",
            "print(",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()

