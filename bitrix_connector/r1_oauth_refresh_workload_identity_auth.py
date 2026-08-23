"""Gate hermético para la identidad de carga de trabajo del endpoint R1.

La verificación criptográfica real se inyectará en el borde HTTP futuro. Este
módulo no lee configuración ni tokens, y sólo acepta la atestación saneada que
ese verificador haya producido dentro del servidor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


@dataclass(frozen=True)
class R1InternalWorkloadIdentityPolicy:
    issuer: str
    audience: str
    authorized_client_id: str
    maximum_token_age_seconds: int = 300


@dataclass(frozen=True)
class R1ValidatedWorkloadIdentity:
    """Resultado interno de un verificador de firma; nunca un payload HTTP."""

    issuer: str
    audience: str
    client_id: str
    subject: str
    authenticated_at: datetime
    expires_at: datetime
    signature_validated: Literal[True] = True


def build_r1_internal_workload_identity_policy(
    *, issuer: str, audience: str, authorized_client_id: str
) -> R1InternalWorkloadIdentityPolicy:
    """Construye una política explícita sin cargar secretos ni App Settings."""

    return R1InternalWorkloadIdentityPolicy(
        issuer=issuer,
        audience=audience,
        authorized_client_id=authorized_client_id,
    )


def validate_r1_internal_workload_identity_once(
    policy: R1InternalWorkloadIdentityPolicy,
    identity: R1ValidatedWorkloadIdentity | None,
    *,
    now: datetime,
) -> bool:
    """Aplica el allowlist y la ventana temporal tras validar la firma."""

    if (
        type(policy) is not R1InternalWorkloadIdentityPolicy
        or type(identity) is not R1ValidatedWorkloadIdentity
        or type(now) is not datetime
        or now.tzinfo is None
        or not all(
            value.strip()
            for value in (
                policy.issuer,
                policy.audience,
                policy.authorized_client_id,
                identity.issuer,
                identity.audience,
                identity.client_id,
                identity.subject,
            )
        )
        or policy.maximum_token_age_seconds <= 0
        or identity.signature_validated is not True
        or identity.issuer != policy.issuer
        or identity.audience != policy.audience
        or identity.client_id != policy.authorized_client_id
        or identity.authenticated_at.tzinfo is None
        or identity.expires_at.tzinfo is None
    ):
        return False

    now_utc = now.astimezone(timezone.utc)
    authenticated_at = identity.authenticated_at.astimezone(timezone.utc)
    expires_at = identity.expires_at.astimezone(timezone.utc)
    return bool(
        authenticated_at <= now_utc <= expires_at
        and (now_utc - authenticated_at).total_seconds()
        <= policy.maximum_token_age_seconds
    )


__all__ = [
    "R1InternalWorkloadIdentityPolicy",
    "R1ValidatedWorkloadIdentity",
    "build_r1_internal_workload_identity_policy",
    "validate_r1_internal_workload_identity_once",
]
