"""Bounded, sanitized coordinator for the read-only R1 Azure diagnostic envelope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


MAX_ENVELOPE_ATTEMPTS = 3
MAX_READS_PER_ATTEMPT = 8
MAX_HEALTH_PAIRS_PER_ATTEMPT = 1

AttemptState = Literal[
    "GO",
    "NO-GO-RECOVERABLE",
    "AUTHENTICATION-REQUIRED",
    "NO-GO-TERMINAL",
]
EnvelopeState = Literal[
    "GO",
    "ATTENTION-REQUIRED-AZURE-AUTHENTICATION",
    "NO-GO-BUDGET-EXHAUSTED",
    "NO-GO-TERMINAL",
]

_ALLOWED_CATEGORIES = {
    "none",
    "authentication",
    "authorization",
    "not_found",
    "transport",
    "unknown",
    "drift",
    "invalid_evidence",
    "resource_close_failed",
}


@dataclass(frozen=True)
class R1AzureDiagnosticAttemptResult:
    state: AttemptState
    category: str
    read_calls: int
    health_pairs: int


class R1AzureDiagnosticAttempt(Protocol):
    async def run_once(self) -> R1AzureDiagnosticAttemptResult: ...

    async def close(self) -> None: ...


class R1AzureDiagnosticAttemptFactory(Protocol):
    def __call__(self, attempt_number: int) -> R1AzureDiagnosticAttempt: ...


@dataclass(frozen=True)
class R1AzureDiagnosticEnvelopeResult:
    state: EnvelopeState
    category: str
    attempts_started: int
    read_calls: int
    health_pairs: int
    resources_closed: bool
    mutations: Literal[0] = 0
    protected_source_opens: Literal[0] = 0
    secret_reads: Literal[0] = 0


def _valid_attempt_result(result: object) -> bool:
    return bool(
        type(result) is R1AzureDiagnosticAttemptResult
        and result.state in (
            "GO",
            "NO-GO-RECOVERABLE",
            "AUTHENTICATION-REQUIRED",
            "NO-GO-TERMINAL",
        )
        and result.category in _ALLOWED_CATEGORIES
        and type(result.read_calls) is int
        and 0 <= result.read_calls <= MAX_READS_PER_ATTEMPT
        and type(result.health_pairs) is int
        and 0 <= result.health_pairs <= MAX_HEALTH_PAIRS_PER_ATTEMPT
        and (result.state != "GO" or result.category == "none")
        and (
            result.state != "AUTHENTICATION-REQUIRED"
            or result.category == "authentication"
        )
    )


class R1AzureDiagnosticCoordinator:
    """Runs fresh one-shot attempts inside one finite conversational envelope."""

    __slots__ = ("_attempt_factory", "_max_attempts", "_used")

    def __init__(
        self,
        *,
        attempt_factory: R1AzureDiagnosticAttemptFactory,
        max_attempts: int = MAX_ENVELOPE_ATTEMPTS,
    ) -> None:
        if not callable(attempt_factory):
            raise TypeError("r1_azure_diagnostic_attempt_factory_invalid")
        if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ENVELOPE_ATTEMPTS:
            raise ValueError("r1_azure_diagnostic_attempt_budget_invalid")
        self._attempt_factory = attempt_factory
        self._max_attempts = max_attempts
        self._used = False

    async def run_once(self) -> R1AzureDiagnosticEnvelopeResult:
        if self._used:
            raise RuntimeError("r1_azure_diagnostic_coordinator_reused")
        self._used = True
        attempts_started = 0
        read_calls = 0
        health_pairs = 0
        last_recoverable_category = "unknown"

        for attempt_number in range(1, self._max_attempts + 1):
            attempt = None
            result = None
            close_ok = True
            attempts_started += 1
            try:
                attempt = self._attempt_factory(attempt_number)
                if (
                    not callable(getattr(attempt, "run_once", None))
                    or not callable(getattr(attempt, "close", None))
                ):
                    raise TypeError("r1_azure_diagnostic_attempt_invalid")
                result = await attempt.run_once()
            except BaseException:
                result = None
            finally:
                if attempt is not None and callable(getattr(attempt, "close", None)):
                    try:
                        await attempt.close()
                    except BaseException:
                        close_ok = False

            if not close_ok:
                return R1AzureDiagnosticEnvelopeResult(
                    state="NO-GO-TERMINAL",
                    category="resource_close_failed",
                    attempts_started=attempts_started,
                    read_calls=read_calls,
                    health_pairs=health_pairs,
                    resources_closed=False,
                )
            if not _valid_attempt_result(result):
                return R1AzureDiagnosticEnvelopeResult(
                    state="NO-GO-TERMINAL",
                    category="invalid_evidence",
                    attempts_started=attempts_started,
                    read_calls=read_calls,
                    health_pairs=health_pairs,
                    resources_closed=True,
                )

            read_calls += result.read_calls
            health_pairs += result.health_pairs
            if result.state == "GO":
                return R1AzureDiagnosticEnvelopeResult(
                    state="GO",
                    category="none",
                    attempts_started=attempts_started,
                    read_calls=read_calls,
                    health_pairs=health_pairs,
                    resources_closed=True,
                )
            if result.state == "AUTHENTICATION-REQUIRED":
                return R1AzureDiagnosticEnvelopeResult(
                    state="ATTENTION-REQUIRED-AZURE-AUTHENTICATION",
                    category="authentication",
                    attempts_started=attempts_started,
                    read_calls=read_calls,
                    health_pairs=health_pairs,
                    resources_closed=True,
                )
            if result.state == "NO-GO-TERMINAL":
                return R1AzureDiagnosticEnvelopeResult(
                    state="NO-GO-TERMINAL",
                    category=result.category,
                    attempts_started=attempts_started,
                    read_calls=read_calls,
                    health_pairs=health_pairs,
                    resources_closed=True,
                )
            last_recoverable_category = result.category

        return R1AzureDiagnosticEnvelopeResult(
            state="NO-GO-BUDGET-EXHAUSTED",
            category=last_recoverable_category,
            attempts_started=attempts_started,
            read_calls=read_calls,
            health_pairs=health_pairs,
            resources_closed=True,
        )


__all__ = [
    "MAX_ENVELOPE_ATTEMPTS",
    "MAX_HEALTH_PAIRS_PER_ATTEMPT",
    "MAX_READS_PER_ATTEMPT",
    "R1AzureDiagnosticAttemptResult",
    "R1AzureDiagnosticCoordinator",
    "R1AzureDiagnosticEnvelopeResult",
]
