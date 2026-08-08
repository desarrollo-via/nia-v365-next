"""Composición M68 hermética de la evidencia conjunta del preflight R1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from .bitrix_history_r0_dormant_confirmation_coordinator import (
    InjectedFreshPreflightEvidence,
)
from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .bitrix_history_r0_runner import BitrixHistoryR0Status
from .bot_v2_preflight import BotV2PreflightResult, BotV2PreflightStatus
from .openline_pilot_preflight import OpenLinePreflightResult, OpenLinePreflightStatus


@dataclass(frozen=True)
class InjectedClosedProbeResult:
    value: object
    resources_closed: bool = True
    external_calls: int = 0


ClosedProbe = Callable[[], Awaitable[InjectedClosedProbeResult]]


class CombinedR1PreflightAdapter:
    """Consume tres sondas una vez y retiene sólo el ancla validada."""

    def __init__(
        self,
        *,
        bot_probe: ClosedProbe,
        openline_probe: ClosedProbe,
        history_probe: ClosedProbe,
    ) -> None:
        if not all(callable(item) for item in (bot_probe, openline_probe, history_probe)):
            raise TypeError("combined_preflight_dependency_invalid")
        self._probes: Optional[tuple[ClosedProbe, ClosedProbe, ClosedProbe]] = (
            bot_probe,
            openline_probe,
            history_probe,
        )
        self._history_outcome: Optional[BitrixHistoryR0PreflightOutcome] = None
        self._used = False
        self._taken = False

    @staticmethod
    def _closed_value(raw: object, expected_type: type) -> object:
        if (
            type(raw) is not InjectedClosedProbeResult
            or raw.resources_closed is not True
            or raw.external_calls != 0
            or type(raw.value) is not expected_type
        ):
            raise ValueError("combined_preflight_probe_invalid")
        return raw.value

    async def probe_once(self) -> InjectedFreshPreflightEvidence:
        if self._used or self._probes is None:
            self.clear()
            raise RuntimeError("combined_preflight_reuse_invalid")
        self._used = True
        try:
            bot = self._closed_value(await self._probes[0](), BotV2PreflightResult)
            if (
                bot.status is not BotV2PreflightStatus.EXISTING_COMPATIBLE
                or bot.rest_revision is None
                or bot.rest_revision <= 0
                or bot.existing_bot_id != 373259
                or bot.registration_needed
            ):
                raise ValueError("combined_preflight_bot_drift")

            line = self._closed_value(await self._probes[1](), OpenLinePreflightResult)
            config = line.config
            if (
                line.status is not OpenLinePreflightStatus.READY
                or line.chat_id != 78733
                or line.dialog_id != "chat78733"
                or config is None
                or config.config_id != 13
                or config.active != "Y"
                or config.welcome_bot_enable != "Y"
                or config.welcome_bot_join != "always"
                or config.welcome_bot_id != 245339
                or config.welcome_bot_time != 0
                or config.welcome_bot_left != "close"
                or any(
                    value != 0
                    for value in (
                        config.no_answer_bot_id,
                        config.close_bot_id,
                        config.auto_close_bot_id,
                        config.worktime_dayoff_bot_id,
                    )
                )
            ):
                raise ValueError("combined_preflight_openline_drift")

            history = self._closed_value(
                await self._probes[2](), BitrixHistoryR0PreflightOutcome
            )
            result = history.result
            if (
                result.status is not BitrixHistoryR0Status.READY
                or result.reason != "bitrix_history_preflight_ready"
                or result.dialog_read_calls != 1
                or result.history_read_calls != 0
                or not result.dialog_verified
                or not result.session_verified
                or not result.baseline_captured
                or not result.resources_closed
                or history.identity_diagnostic is not None
                or not history.anchor_available
            ):
                raise ValueError("combined_preflight_history_drift")
            history.require_anchor()
            self._history_outcome = history
            self._probes = None
            return InjectedFreshPreflightEvidence()
        except BaseException:
            self.clear()
            raise

    def take_history_outcome_once(self) -> BitrixHistoryR0PreflightOutcome:
        outcome = self._history_outcome
        if outcome is None or self._taken:
            self.clear()
            raise RuntimeError("combined_preflight_anchor_unavailable")
        self._taken = True
        self._history_outcome = None
        return outcome

    def clear(self) -> None:
        self._probes = None
        self._history_outcome = None

    @property
    def cleared(self) -> bool:
        return self._probes is None and self._history_outcome is None


__all__ = ["CombinedR1PreflightAdapter", "InjectedClosedProbeResult"]
