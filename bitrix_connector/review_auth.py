"""Autenticador puro y aislado para un único revisor controlado."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, model_validator

from .review_approval import ReviewPrincipal


MIN_REVIEW_TOKEN_CHARS = 24


class ReviewAuthenticationOutcome(str, Enum):
    AUTHENTICATED = "authenticated"
    UNAUTHORIZED = "unauthorized"
    UNAVAILABLE = "unavailable"


class ReviewAuthenticationResult(BaseModel):
    """Resultado seguro; nunca incluye la credencial recibida o configurada."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReviewAuthenticationOutcome
    reason: str
    principal: Optional[ReviewPrincipal] = None

    @model_validator(mode="after")
    def validate_principal(self) -> "ReviewAuthenticationResult":
        authenticated = self.outcome is ReviewAuthenticationOutcome.AUTHENTICATED
        if authenticated != (self.principal is not None):
            raise ValueError("review_auth_principal_outcome_mismatch")
        return self

    @property
    def accepted(self) -> bool:
        return self.outcome is ReviewAuthenticationOutcome.AUTHENTICATED


class SingleReviewerAuthenticator:
    """Compara un Bearer y deriva la identidad solo desde configuración propia."""

    def __init__(
        self,
        *,
        review_token: Optional[str],
        actor: Optional[str],
        credential_id: Optional[str],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        token = (review_token or "").strip()
        self._token = SecretStr(token) if token else None
        self._actor = (actor or "").strip()
        self._credential_id = (credential_id or "").strip()
        self._clock = clock
        self._configuration_valid = self._validate_configuration(token)

    @property
    def configured(self) -> bool:
        return self._configuration_valid

    def _validate_configuration(self, token: str) -> bool:
        if len(token) < MIN_REVIEW_TOKEN_CHARS:
            return False
        try:
            ReviewPrincipal(
                actor=self._actor,
                credential_id=self._credential_id,
                authenticated_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
        except ValidationError:
            return False
        return True

    def authenticate(self, authorization: str) -> ReviewAuthenticationResult:
        if not self._configuration_valid or self._token is None:
            return ReviewAuthenticationResult(
                outcome=ReviewAuthenticationOutcome.UNAVAILABLE,
                reason="review_auth_not_configured",
            )

        scheme, separator, received = (authorization or "").partition(" ")
        candidate = received.strip() if separator and scheme.lower() == "bearer" else ""
        authenticated = hmac.compare_digest(
            candidate.encode("utf-8"),
            self._token.get_secret_value().encode("utf-8"),
        )
        if not authenticated:
            return ReviewAuthenticationResult(
                outcome=ReviewAuthenticationOutcome.UNAUTHORIZED,
                reason="review_unauthorized",
            )

        try:
            principal = ReviewPrincipal(
                actor=self._actor,
                credential_id=self._credential_id,
                authenticated_at=self._clock(),
            )
        except (TypeError, ValueError, ValidationError):
            return ReviewAuthenticationResult(
                outcome=ReviewAuthenticationOutcome.UNAVAILABLE,
                reason="review_auth_clock_invalid",
            )
        return ReviewAuthenticationResult(
            outcome=ReviewAuthenticationOutcome.AUTHENTICATED,
            reason="review_authenticated",
            principal=principal,
        )
