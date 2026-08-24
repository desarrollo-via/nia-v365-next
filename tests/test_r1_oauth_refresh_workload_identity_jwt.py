import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from bitrix_connector.r1_oauth_refresh_workload_identity_auth import (
    build_r1_internal_workload_identity_policy,
)
from bitrix_connector.r1_oauth_refresh_workload_identity_jwt import (
    verify_r1_workload_identity_jwt_once,
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _token(private_key, claims, *, kid="fixture-key"):
    header = _b64(json.dumps({"alg": "RS256", "kid": kid}).encode())
    payload = _b64(json.dumps(claims).encode())
    signature = private_key.sign(
        f"{header}.{payload}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return f"{header}.{payload}.{_b64(signature)}"


class R1WorkloadIdentityJwtTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = self.private_key.public_key().public_numbers()
        self.jwks = {
            "fixture-key": {
                "kty": "RSA",
                "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": _b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        }
        self.policy = build_r1_internal_workload_identity_policy(
            issuer="issuer-fixture",
            audience="audience-fixture",
            authorized_client_id="client-fixture",
        )

    def _claims(self, **overrides):
        claims = {
            "iss": "issuer-fixture",
            "aud": "audience-fixture",
            "azp": "client-fixture",
            "sub": "workload-fixture",
            "iat": int(self.now.timestamp()),
            "exp": int((self.now + timedelta(minutes=4)).timestamp()),
        }
        claims.update(overrides)
        return claims

    def test_accepts_signed_rs256_token_with_exact_claims(self):
        identity = verify_r1_workload_identity_jwt_once(
            _token(self.private_key, self._claims()),
            policy=self.policy,
            jwks_by_kid=self.jwks,
            now=self.now,
        )
        self.assertIsNotNone(identity)
        self.assertEqual(identity.subject, "workload-fixture")

    def test_rejects_tampered_signature_or_wrong_authorized_client(self):
        token = _token(self.private_key, self._claims())
        signed, signature = token.rsplit(".", 1)
        tampered = f"{signed}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
        self.assertIsNone(
            verify_r1_workload_identity_jwt_once(
                tampered, policy=self.policy, jwks_by_kid=self.jwks, now=self.now
            )
        )
        self.assertIsNone(
            verify_r1_workload_identity_jwt_once(
                _token(self.private_key, self._claims(azp="other-client")),
                policy=self.policy,
                jwks_by_kid=self.jwks,
                now=self.now,
            )
        )

    def test_rejects_expired_or_stale_token(self):
        self.assertIsNone(
            verify_r1_workload_identity_jwt_once(
                _token(
                    self.private_key,
                    self._claims(
                        iat=int((self.now - timedelta(minutes=6)).timestamp()),
                        exp=int((self.now + timedelta(minutes=1)).timestamp()),
                    ),
                ),
                policy=self.policy,
                jwks_by_kid=self.jwks,
                now=self.now,
            )
        )
        self.assertIsNone(
            verify_r1_workload_identity_jwt_once(
                _token(
                    self.private_key,
                    self._claims(exp=int((self.now - timedelta(seconds=1)).timestamp())),
                ),
                policy=self.policy,
                jwks_by_kid=self.jwks,
                now=self.now,
            )
        )


if __name__ == "__main__":
    unittest.main()
