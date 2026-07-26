"""Sesiones administrativas efímeras para el Review Lab.

El almacén conserva únicamente hashes de los identificadores y del token CSRF.
No conoce Bearer, HTTP, MongoDB ni configuración del conector.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional

from .review_approval import ReviewPrincipal


SESSION_COOKIE_NAME = "__Host-nia_review_session"
DEFAULT_IDLE_TIMEOUT = timedelta(minutes=10)
DEFAULT_ABSOLUTE_TIMEOUT = timedelta(minutes=30)
MIN_OPAQUE_TOKEN_CHARS = 32


class ReviewAdminSessionOutcome(str, Enum):
    AUTHENTICATED = "authenticated"
    MISSING = "missing"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class IssuedReviewAdminSession:
    session_id: str
    csrf_token: str
    principal: ReviewPrincipal
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True)
class ReviewAdminSessionResolution:
    outcome: ReviewAdminSessionOutcome
    principal: Optional[ReviewPrincipal] = None
    idle_expires_at: Optional[datetime] = None
    absolute_expires_at: Optional[datetime] = None

    @property
    def authenticated(self) -> bool:
        return self.outcome is ReviewAdminSessionOutcome.AUTHENTICATED


@dataclass
class _StoredReviewAdminSession:
    session_hash: str
    csrf_hash: str
    principal: ReviewPrincipal
    created_at: datetime
    last_seen_at: datetime
    absolute_expires_at: datetime
    revoked: bool = False


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review_admin_clock_must_be_aware")
    return value.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class InMemoryReviewAdminSessionStore:
    """Almacén de un solo operador; reinicio o cierre revoca todo."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        idle_timeout: timedelta = DEFAULT_IDLE_TIMEOUT,
        absolute_timeout: timedelta = DEFAULT_ABSOLUTE_TIMEOUT,
    ) -> None:
        if idle_timeout <= timedelta(0):
            raise ValueError("review_admin_idle_timeout_invalid")
        if absolute_timeout <= idle_timeout:
            raise ValueError("review_admin_absolute_timeout_invalid")
        self._clock = clock
        self._token_factory = token_factory
        self._idle_timeout = idle_timeout
        self._absolute_timeout = absolute_timeout
        self._sessions: dict[str, _StoredReviewAdminSession] = {}
        self._closed = False

    @property
    def active_count(self) -> int:
        return sum(not item.revoked for item in self._sessions.values())

    @property
    def closed(self) -> bool:
        return self._closed

    def issue(self, principal: ReviewPrincipal) -> IssuedReviewAdminSession:
        if self._closed:
            raise RuntimeError("review_admin_session_store_closed")
        now = _utc(self._clock())
        session_id = self._new_token()
        csrf_token = self._new_token()
        session_hash = _digest(session_id)
        if session_hash in self._sessions:
            raise RuntimeError("review_admin_session_token_collision")

        self.revoke_all()
        absolute_expires_at = now + self._absolute_timeout
        record = _StoredReviewAdminSession(
            session_hash=session_hash,
            csrf_hash=_digest(csrf_token),
            principal=principal,
            created_at=now,
            last_seen_at=now,
            absolute_expires_at=absolute_expires_at,
        )
        self._sessions[session_hash] = record
        return IssuedReviewAdminSession(
            session_id=session_id,
            csrf_token=csrf_token,
            principal=principal,
            idle_expires_at=now + self._idle_timeout,
            absolute_expires_at=absolute_expires_at,
        )

    def resolve(
        self,
        session_id: Optional[str],
        *,
        csrf_token: Optional[str] = None,
        require_csrf: bool = False,
        touch: bool = True,
    ) -> ReviewAdminSessionResolution:
        if self._closed:
            return ReviewAdminSessionResolution(
                outcome=ReviewAdminSessionOutcome.UNAVAILABLE
            )
        if not session_id:
            return ReviewAdminSessionResolution(
                outcome=ReviewAdminSessionOutcome.MISSING
            )
        record = self._sessions.get(_digest(session_id))
        if record is None:
            return ReviewAdminSessionResolution(
                outcome=ReviewAdminSessionOutcome.MISSING
            )
        if record.revoked:
            return ReviewAdminSessionResolution(
                outcome=ReviewAdminSessionOutcome.REVOKED
            )

        now = _utc(self._clock())
        idle_expires_at = record.last_seen_at + self._idle_timeout
        if now >= record.absolute_expires_at or now >= idle_expires_at:
            record.revoked = True
            return ReviewAdminSessionResolution(
                outcome=ReviewAdminSessionOutcome.EXPIRED
            )
        if require_csrf and not self._valid_csrf(record, csrf_token):
            return ReviewAdminSessionResolution(
                outcome=ReviewAdminSessionOutcome.MISSING
            )
        if touch:
            record.last_seen_at = now
            idle_expires_at = min(
                now + self._idle_timeout,
                record.absolute_expires_at,
            )
        return ReviewAdminSessionResolution(
            outcome=ReviewAdminSessionOutcome.AUTHENTICATED,
            principal=record.principal,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=record.absolute_expires_at,
        )

    def revoke(self, session_id: Optional[str]) -> bool:
        if not session_id:
            return False
        record = self._sessions.get(_digest(session_id))
        if record is None or record.revoked:
            return False
        record.revoked = True
        return True

    def rotate_csrf(self, session_id: Optional[str]) -> Optional[str]:
        resolution = self.resolve(session_id, touch=False)
        if not resolution.authenticated or not session_id:
            return None
        record = self._sessions.get(_digest(session_id))
        if record is None or record.revoked:
            return None
        csrf_token = self._new_token()
        record.csrf_hash = _digest(csrf_token)
        return csrf_token

    def revoke_all(self) -> None:
        for record in self._sessions.values():
            record.revoked = True

    async def close(self) -> None:
        self.revoke_all()
        self._sessions.clear()
        self._closed = True

    def _new_token(self) -> str:
        token = self._token_factory()
        if not isinstance(token, str) or len(token) < MIN_OPAQUE_TOKEN_CHARS:
            raise RuntimeError("review_admin_token_factory_invalid")
        return token

    @staticmethod
    def _valid_csrf(
        record: _StoredReviewAdminSession,
        csrf_token: Optional[str],
    ) -> bool:
        candidate = _digest(csrf_token or "")
        return hmac.compare_digest(candidate, record.csrf_hash)


__all__ = [
    "DEFAULT_ABSOLUTE_TIMEOUT",
    "DEFAULT_IDLE_TIMEOUT",
    "InMemoryReviewAdminSessionStore",
    "IssuedReviewAdminSession",
    "ReviewAdminSessionOutcome",
    "ReviewAdminSessionResolution",
    "SESSION_COOKIE_NAME",
]
