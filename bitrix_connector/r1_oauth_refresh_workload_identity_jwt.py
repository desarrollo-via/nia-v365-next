"""Verificador RS256 inyectable para el borde futuro de R1.

No obtiene JWKS, no lee configuración y no monta HTTP. El llamador debe aportar
una política explícita y la clave pública ya resuelta por un componente de
borde autorizado.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .r1_oauth_refresh_workload_identity_auth import (
    R1InternalWorkloadIdentityPolicy,
    R1ValidatedWorkloadIdentity,
)


def _decode_base64url(value: str) -> bytes | None:
    if type(value) is not str or not value or len(value) > 8192:
        return None
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error):
        return None


def _decode_json_object(value: str) -> dict[str, object] | None:
    decoded = _decode_base64url(value)
    if decoded is None:
        return None
    try:
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if type(parsed) is dict else None


def _rsa_public_key_from_jwk(jwk: Mapping[str, object]) -> rsa.RSAPublicKey | None:
    if (
        jwk.get("kty") != "RSA"
        or type(jwk.get("n")) is not str
        or type(jwk.get("e")) is not str
    ):
        return None
    modulus = _decode_base64url(jwk["n"])
    exponent = _decode_base64url(jwk["e"])
    if modulus is None or exponent is None:
        return None
    try:
        return rsa.RSAPublicNumbers(
            int.from_bytes(exponent, "big"), int.from_bytes(modulus, "big")
        ).public_key()
    except ValueError:
        return None


def verify_r1_workload_identity_jwt_once(
    token: str,
    *,
    policy: R1InternalWorkloadIdentityPolicy,
    jwks_by_kid: Mapping[str, Mapping[str, object]],
    now: datetime,
) -> R1ValidatedWorkloadIdentity | None:
    """Verifica una vez firma RS256 y claims; nunca expone el token."""

    if (
        type(token) is not str
        or type(policy) is not R1InternalWorkloadIdentityPolicy
        or type(now) is not datetime
        or now.tzinfo is None
        or not isinstance(jwks_by_kid, Mapping)
    ):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header = _decode_json_object(parts[0])
    claims = _decode_json_object(parts[1])
    signature = _decode_base64url(parts[2])
    if (
        header is None
        or claims is None
        or signature is None
        or header.get("alg") != "RS256"
        or type(header.get("kid")) is not str
    ):
        return None
    jwk = jwks_by_kid.get(header["kid"])
    if not isinstance(jwk, Mapping):
        return None
    public_key = _rsa_public_key_from_jwk(jwk)
    if public_key is None:
        return None
    try:
        public_key.verify(
            signature,
            f"{parts[0]}.{parts[1]}".encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, UnicodeEncodeError):
        return None

    expected = ("iss", "aud", "azp", "sub")
    if any(type(claims.get(name)) is not str for name in expected):
        return None
    issued_at = claims.get("iat")
    expires_at = claims.get("exp")
    if type(issued_at) is not int or type(expires_at) is not int:
        return None
    try:
        authenticated_at = datetime.fromtimestamp(issued_at, tz=timezone.utc)
        expires = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    now_utc = now.astimezone(timezone.utc)
    if (
        claims["iss"] != policy.issuer
        or claims["aud"] != policy.audience
        or claims["azp"] != policy.authorized_client_id
        or not claims["sub"].strip()
        or authenticated_at > now_utc
        or now_utc > expires
        or (now_utc - authenticated_at).total_seconds()
        > policy.maximum_token_age_seconds
    ):
        return None
    return R1ValidatedWorkloadIdentity(
        issuer=claims["iss"],
        audience=claims["aud"],
        client_id=claims["azp"],
        subject=claims["sub"],
        authenticated_at=authenticated_at,
        expires_at=expires,
    )


__all__ = ["verify_r1_workload_identity_jwt_once"]
