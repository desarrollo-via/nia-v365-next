"""Hermetic day-bound envelope for the exact remote read-only R1 preflight."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from .r1_azure_diagnostic_coordinator import (
    MAX_ENVELOPE_ATTEMPTS,
    MAX_HEALTH_PAIRS_PER_ATTEMPT,
    MAX_READS_PER_ATTEMPT,
    R1AzureDiagnosticCoordinator,
)


REMOTE_PREFLIGHT_EAOR_ID = (
    "NIA-NEXT-R1-REMOTE-PREFLIGHT-EAOR-2026-08-13-V1"
)
REMOTE_PREFLIGHT_EAOR_DAY = "2026-08-13"
REMOTE_PREFLIGHT_ACCEPTANCE = "sp"

RemotePreflightState = Literal[
    "INERT",
    "NO-GO-ACCEPTANCE",
    "NO-GO-EXPIRED",
    "GO-REMOTE-PREFLIGHT",
    "ATTENTION-REQUIRED-AZURE-AUTHENTICATION",
    "NO-GO-BUDGET-EXHAUSTED",
    "NO-GO-TERMINAL",
]


@dataclass(frozen=True)
class R1RemotePreflightEaorSnapshot:
    state: RemotePreflightState = "INERT"
    eaor_id: str = REMOTE_PREFLIGHT_EAOR_ID
    envelope_day: str = REMOTE_PREFLIGHT_EAOR_DAY
    evaluated_day: str = ""
    acceptance_calls: int = 0
    diagnostic_constructions: int = 0
    attempts_started: int = 0
    read_calls: int = 0
    health_pairs: int = 0
    resources_closed: bool = False
    category: str = "none"
    max_attempts: Literal[3] = MAX_ENVELOPE_ATTEMPTS
    max_reads_per_attempt: Literal[8] = MAX_READS_PER_ATTEMPT
    max_health_pairs_per_attempt: Literal[1] = MAX_HEALTH_PAIRS_PER_ATTEMPT
    mutations: Literal[0] = 0
    protected_source_opens: Literal[0] = 0
    secret_reads: Literal[0] = 0
    app_setting_lists: Literal[0] = 0
    broad_resource_lists: Literal[0] = 0
    bitrix_calls: Literal[0] = 0
    messages_sent: Literal[0] = 0


class R1RemotePreflightEaorCoordinator:
    """Lazily creates the existing diagnostic only after day and acceptance gates."""

    __slots__ = ("_diagnostic_factory", "_used")

    def __init__(
        self,
        *,
        diagnostic_factory: Callable[[], R1AzureDiagnosticCoordinator],
    ) -> None:
        if not callable(diagnostic_factory):
            raise TypeError("r1_remote_preflight_diagnostic_factory_invalid")
        self._diagnostic_factory = diagnostic_factory
        self._used = False

    def preview(self) -> R1RemotePreflightEaorSnapshot:
        return R1RemotePreflightEaorSnapshot()

    async def run_once(
        self,
        *,
        acceptance: str,
        current_day: str,
    ) -> R1RemotePreflightEaorSnapshot:
        if self._used:
            raise RuntimeError("r1_remote_preflight_eaor_reused")
        self._used = True
        if acceptance != REMOTE_PREFLIGHT_ACCEPTANCE:
            self._diagnostic_factory = None
            return R1RemotePreflightEaorSnapshot(
                state="NO-GO-ACCEPTANCE",
                evaluated_day=current_day,
                acceptance_calls=1,
                resources_closed=True,
            )
        if current_day != REMOTE_PREFLIGHT_EAOR_DAY:
            self._diagnostic_factory = None
            return R1RemotePreflightEaorSnapshot(
                state="NO-GO-EXPIRED",
                evaluated_day=current_day,
                acceptance_calls=1,
                resources_closed=True,
                category="drift",
            )
        factory, self._diagnostic_factory = self._diagnostic_factory, None
        try:
            diagnostic = factory() if factory is not None else None
            if type(diagnostic) is not R1AzureDiagnosticCoordinator:
                raise TypeError("r1_remote_preflight_diagnostic_invalid")
            result = await diagnostic.run_once()
        except BaseException:
            return R1RemotePreflightEaorSnapshot(
                state="NO-GO-TERMINAL",
                evaluated_day=current_day,
                acceptance_calls=1,
                diagnostic_constructions=1,
                resources_closed=False,
                category="invalid_evidence",
            )
        states = {
            "GO": "GO-REMOTE-PREFLIGHT",
            "ATTENTION-REQUIRED-AZURE-AUTHENTICATION": (
                "ATTENTION-REQUIRED-AZURE-AUTHENTICATION"
            ),
            "NO-GO-BUDGET-EXHAUSTED": "NO-GO-BUDGET-EXHAUSTED",
            "NO-GO-TERMINAL": "NO-GO-TERMINAL",
        }
        state = states.get(result.state, "NO-GO-TERMINAL")
        return R1RemotePreflightEaorSnapshot(
            state=state,
            evaluated_day=current_day,
            acceptance_calls=1,
            diagnostic_constructions=1,
            attempts_started=result.attempts_started,
            read_calls=result.read_calls,
            health_pairs=result.health_pairs,
            resources_closed=result.resources_closed,
            category=(
                result.category if state != "NO-GO-TERMINAL"
                or result.state == "NO-GO-TERMINAL" else "invalid_evidence"
            ),
        )

    def __repr__(self) -> str:
        return "R1RemotePreflightEaorCoordinator(<redacted>)"


__all__ = [
    "REMOTE_PREFLIGHT_ACCEPTANCE", "REMOTE_PREFLIGHT_EAOR_DAY",
    "REMOTE_PREFLIGHT_EAOR_ID", "R1RemotePreflightEaorCoordinator",
    "R1RemotePreflightEaorSnapshot",
]
