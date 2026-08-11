import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.config import load_settings
from bitrix_connector.r1_key_vault_protected_host_probe import (
    EXPECTED_DISTRIBUTIONS,
    ExactOneShotProtectedHostProbe,
)
from bitrix_connector.review_router import create_review_router


VERSIONS = dict(EXPECTED_DISTRIBUTIONS)
PATH = "/bitrix-connector/review/r1-key-vault-provisioning-preflight"
OLD_PATH = "/bitrix-connector/review/r1-key-vault-host-probe"
HEADERS = {"Authorization": "Bearer review-token-that-is-long-enough"}


class NoEnumerationEnvironment(dict):
    def __iter__(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def keys(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def items(self):
        raise AssertionError("environment_must_not_be_enumerated")

    def values(self):
        raise AssertionError("environment_must_not_be_enumerated")


class UnreachableReviewReader:
    def __getattr__(self, _name):
        raise AssertionError("review_runtime_must_not_be_used")


def probe():
    return ExactOneShotProtectedHostProbe(
        environ=NoEnumerationEnvironment(),
        version_reader=VERSIONS.__getitem__,
    )


def client(*, old_probe=None, provisioning_probe=None):
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
            host_probe=old_probe,
            provisioning_probe=provisioning_probe,
        ),
        prefix="/bitrix-connector",
    )
    return TestClient(app)


class R1KeyVaultProvisioningPreflightRouteTests(unittest.TestCase):
    def test_new_route_is_protected_sanitized_and_one_shot(self):
        with client(provisioning_probe=probe()) as http:
            denied = http.get(PATH)
            first = http.get(PATH, headers=HEADERS)
            second = http.get(PATH, headers=HEADERS)

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["setting_present"])
        self.assertEqual(first.json()["external_calls"], 0)
        self.assertEqual(first.json()["writes"], 0)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            second.json()["detail"],
            "provisioning_probe_already_consumed",
        )

    def test_new_and_consumed_old_probe_are_independent(self):
        old = probe()
        old.collect_once()
        with client(old_probe=old, provisioning_probe=probe()) as http:
            old_response = http.get(OLD_PATH, headers=HEADERS)
            new_response = http.get(PATH, headers=HEADERS)

        self.assertEqual(old_response.status_code, 409)
        self.assertEqual(new_response.status_code, 200)

    def test_unbound_route_fails_closed(self):
        with client() as http:
            response = http.get(PATH, headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "provisioning_probe_not_bound")

    def test_fixed_route_is_not_captured_as_review_event(self):
        with client(provisioning_probe=probe()) as http:
            response = http.get(PATH, headers=HEADERS)
        self.assertEqual(response.status_code, 200)

    def test_productive_router_builds_a_distinct_second_owner(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "bitrix_connector"
            / "router.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "provisioning_preflight_probe = build_protected_host_probe()",
            source,
        )
        self.assertIn(
            "provisioning_probe=provisioning_preflight_probe",
            source,
        )


if __name__ == "__main__":
    unittest.main()
