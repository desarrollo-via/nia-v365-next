import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.r1_oauth_refresh_execution_owner import R1OAuthRefreshSnapshot
from bitrix_connector.r1_oauth_refresh_internal_endpoint import (
    R1_OAUTH_REFRESH_INTERNAL_PATH,
)
from bitrix_connector.r1_oauth_refresh_internal_router import (
    R1OAuthRefreshInternalRouterBindings,
    create_r1_oauth_refresh_internal_router,
)
from bitrix_connector.r1_oauth_refresh_workload_identity_auth import (
    build_r1_internal_workload_identity_policy,
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _token(private_key, claims):
    header = _b64(json.dumps({"alg": "RS256", "kid": "fixture-key"}).encode())
    payload = _b64(json.dumps(claims).encode())
    signature = private_key.sign(
        f"{header}.{payload}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return f"{header}.{payload}.{_b64(signature)}"


class R1OAuthRefreshInternalRouterTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = private_key.public_key().public_numbers()
        self.jwks = {
            "fixture-key": {
                "kty": "RSA",
                "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": _b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        }
        self.token = _token(
            private_key,
            {
                "iss": "issuer-fixture",
                "aud": "audience-fixture",
                "azp": "client-fixture",
                "sub": "workload-fixture",
                "iat": int(self.now.timestamp()),
                "exp": int((self.now + timedelta(minutes=4)).timestamp()),
            },
        )
        self.calls = 0

        async def executor():
            self.calls += 1
            return R1OAuthRefreshSnapshot(state="READY", reason="fixture")

        bindings = R1OAuthRefreshInternalRouterBindings(
            policy=build_r1_internal_workload_identity_policy(
                issuer="issuer-fixture",
                audience="audience-fixture",
                authorized_client_id="client-fixture",
            ),
            jwks_by_kid=self.jwks,
            executor=executor,
            now_provider=lambda: self.now,
        )
        app = FastAPI()
        app.include_router(create_r1_oauth_refresh_internal_router(bindings))
        self.client = TestClient(app)

    def test_valid_bearer_delegates_once(self):
        response = self.client.post(
            R1_OAUTH_REFRESH_INTERNAL_PATH,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "READY")
        self.assertEqual(self.calls, 1)

    def test_missing_or_invalid_bearer_never_invokes_executor(self):
        self.assertEqual(
            self.client.post(R1_OAUTH_REFRESH_INTERNAL_PATH).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                R1_OAUTH_REFRESH_INTERNAL_PATH,
                headers={"Authorization": "Bearer invalid"},
            ).status_code,
            401,
        )
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
