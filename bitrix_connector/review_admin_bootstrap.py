"""Autenticación bootstrap efímera para un primer Review Admin controlado."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Callable

from pydantic import ValidationError

from .review_admin import (
    ReviewAdminAuthenticationOutcome,
    ReviewAdminAuthenticationResult,
)
from .review_approval import ReviewPrincipal


DEFAULT_BOOTSTRAP_TTL = timedelta(minutes=5)
DEFAULT_BOOTSTRAP_MAX_ATTEMPTS = 5
MIN_BOOTSTRAP_CODE_CHARS = 32


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review_admin_bootstrap_clock_must_be_aware")
    return value.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OneTimeReviewAdminAuthenticator:
    """Compara un código una sola vez y no conserva su valor original."""

    def __init__(
        self,
        *,
        bootstrap_code: str,
        actor: str,
        credential_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        ttl: timedelta = DEFAULT_BOOTSTRAP_TTL,
        max_attempts: int = DEFAULT_BOOTSTRAP_MAX_ATTEMPTS,
    ) -> None:
        code = bootstrap_code.strip()
        if len(code) < MIN_BOOTSTRAP_CODE_CHARS:
            raise ValueError("review_admin_bootstrap_code_invalid")
        if ttl <= timedelta(0):
            raise ValueError("review_admin_bootstrap_ttl_invalid")
        if max_attempts < 1:
            raise ValueError("review_admin_bootstrap_attempts_invalid")

        self._clock = clock
        self._created_at = _utc(clock())
        self._expires_at = self._created_at + ttl
        self._code_hash = _digest(code)
        self._actor = actor.strip()
        self._credential_id = credential_id.strip()
        self._max_attempts = max_attempts
        self._failed_attempts = 0
        self._consumed = False
        self._closed = False

        try:
            ReviewPrincipal(
                actor=self._actor,
                credential_id=self._credential_id,
                authenticated_at=self._created_at,
            )
        except ValidationError as exc:
            raise ValueError("review_admin_bootstrap_identity_invalid") from exc

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    @property
    def attempts_remaining(self) -> int:
        return max(0, self._max_attempts - self._failed_attempts)

    @property
    def consumed(self) -> bool:
        return self._consumed

    @property
    def closed(self) -> bool:
        return self._closed

    def authenticate(self, credential: str) -> ReviewAdminAuthenticationResult:
        now = _utc(self._clock())
        if (
            self._closed
            or self._consumed
            or now >= self._expires_at
            or self._failed_attempts >= self._max_attempts
        ):
            return ReviewAdminAuthenticationResult(
                outcome=ReviewAdminAuthenticationOutcome.UNAVAILABLE
            )

        candidate_hash = _digest(credential or "")
        accepted = hmac.compare_digest(candidate_hash, self._code_hash)
        if not accepted:
            self._failed_attempts += 1
            return ReviewAdminAuthenticationResult(
                outcome=ReviewAdminAuthenticationOutcome.UNAUTHORIZED
            )

        self._consumed = True
        self._code_hash = "0" * 64
        try:
            principal = ReviewPrincipal(
                actor=self._actor,
                credential_id=self._credential_id,
                authenticated_at=now,
            )
        except (TypeError, ValueError, ValidationError):
            self._closed = True
            return ReviewAdminAuthenticationResult(
                outcome=ReviewAdminAuthenticationOutcome.UNAVAILABLE
            )
        return ReviewAdminAuthenticationResult(
            outcome=ReviewAdminAuthenticationOutcome.AUTHENTICATED,
            principal=principal,
        )

    def close(self) -> None:
        self._code_hash = "0" * 64
        self._closed = True


__all__ = [
    "DEFAULT_BOOTSTRAP_MAX_ATTEMPTS",
    "DEFAULT_BOOTSTRAP_TTL",
    "MIN_BOOTSTRAP_CODE_CHARS",
    "OneTimeReviewAdminAuthenticator",
]
