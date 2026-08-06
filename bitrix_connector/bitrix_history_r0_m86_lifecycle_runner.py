"""M86-G: runner acotado que conserva el ancla sólo en memoria."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

from .bitrix_history_r0_m86_cross_turn_channel import (
    JsonFileM86AllowlistedStateBackend,
    M86ChannelAction,
    M86ChannelRecord,
    M86ChannelStage,
    M86CrossTurnChannel,
)
from .bitrix_history_r0_m86_source_bound_command import (
    M86SourceBoundCommand,
    build_real_m86_source_bound_command,
)


M86G_MAX_LIFETIME_SECONDS = 300.0
M86G_DEFAULT_POLL_SECONDS = 0.25


@dataclass(frozen=True)
class M86LifecyclePublicEvent:
    phase: Literal["M86-G"]
    state: Literal[
        "PREFLIGHT-READY",
        "MANUAL-REMOVAL-CONFIRMED",
        "SECOND-CONFIRMATION-CONFIRMED",
        "ATTENTION-REQUIRED",
    ]
    sequence: int
    attention_required_now: bool
    human_message_required_now: bool
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


@dataclass(frozen=True)
class M86LifecycleRunnerSnapshot:
    phase: Literal["M86-G"]
    state: Literal[
        "PREPARED",
        "VERIFIED",
        "ROLLED-BACK",
        "NO-GO",
        "CANCELLED",
        "TIMED-OUT",
    ]
    reason: str
    execution_requested: bool
    runner_calls: int
    control_read_calls: int
    sleep_calls: int
    public_event_calls: int
    preflight_ready: bool
    manual_removal_confirmed: bool
    second_confirmation_confirmed: bool
    attention_boundary_reached: bool
    roundtrip_calls: int
    same_private_outcome_handed_off: bool
    waiting_state_consumed: bool
    command_close_verified: bool
    private_anchor_persisted: Literal[False] = False
    private_anchor_exposed: Literal[False] = False
    first_and_second_confirmations_separate: Literal[True] = True
    maximum_lifetime_seconds: float = M86G_MAX_LIFETIME_SECONDS
    poll_interval_seconds: float = M86G_DEFAULT_POLL_SECONDS
    retry_budget: Literal[0] = 0
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    real_authorizations_consumed: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    remaining_real_bindings: Literal[2] = 2
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


ControlReader = Callable[[], Awaitable[Optional[M86ChannelRecord]]]
PublicEventSink = Callable[[M86LifecyclePublicEvent], Awaitable[None]]
RoundtripContinuation = Callable[[object], Awaitable[object]]
Sleeper = Callable[[float], Awaitable[None]]
ChannelFactory = Callable[[], M86CrossTurnChannel]


class M86LifecycleRunner:
    """Un solo proceso posee comando, outcome y continuación hasta el cleanup."""

    __slots__ = (
        "_channel_factory",
        "_command",
        "_control_reader",
        "_event_sink",
        "_execution_enabled",
        "_lifetime_seconds",
        "_poll_seconds",
        "_roundtrip",
        "_sleeper",
        "_used",
    )

    def __init__(
        self,
        *,
        command: M86SourceBoundCommand,
        control_reader: ControlReader,
        channel_factory: ChannelFactory,
        event_sink: PublicEventSink,
        roundtrip_continuation: RoundtripContinuation,
        sleeper: Sleeper = asyncio.sleep,
        execution_enabled: bool = False,
        lifetime_seconds: float = M86G_MAX_LIFETIME_SECONDS,
        poll_seconds: float = M86G_DEFAULT_POLL_SECONDS,
    ) -> None:
        if (
            type(command) is not M86SourceBoundCommand
            or not all(
                callable(value)
                for value in (
                    control_reader,
                    channel_factory,
                    event_sink,
                    roundtrip_continuation,
                    sleeper,
                )
            )
            or type(execution_enabled) is not bool
            or type(lifetime_seconds) not in (int, float)
            or lifetime_seconds <= 0
            or lifetime_seconds > M86G_MAX_LIFETIME_SECONDS
            or type(poll_seconds) not in (int, float)
            or poll_seconds <= 0
            or poll_seconds > 5
        ):
            raise TypeError("m86g_runner_dependency_invalid")
        self._command: Optional[M86SourceBoundCommand] = command
        self._control_reader: Optional[ControlReader] = control_reader
        self._channel_factory: Optional[ChannelFactory] = channel_factory
        self._event_sink: Optional[PublicEventSink] = event_sink
        self._roundtrip: Optional[RoundtripContinuation] = roundtrip_continuation
        self._sleeper: Optional[Sleeper] = sleeper
        self._execution_enabled = execution_enabled
        self._lifetime_seconds = float(lifetime_seconds)
        self._poll_seconds = float(poll_seconds)
        self._used = False

    def __repr__(self) -> str:
        return "M86LifecycleRunner(<redacted>)"

    def _snapshot(
        self,
        *,
        state: str,
        reason: str,
        execution_requested: bool,
        runner_calls: int = 0,
        control_read_calls: int = 0,
        sleep_calls: int = 0,
        public_event_calls: int = 0,
        preflight_ready: bool = False,
        manual_removal_confirmed: bool = False,
        second_confirmation_confirmed: bool = False,
        attention_boundary_reached: bool = False,
        roundtrip_calls: int = 0,
        same_private_outcome_handed_off: bool = False,
        waiting_state_consumed: bool = False,
        command_close_verified: bool = True,
    ) -> M86LifecycleRunnerSnapshot:
        return M86LifecycleRunnerSnapshot(
            phase="M86-G",
            state=state,
            reason=reason,
            execution_requested=execution_requested,
            runner_calls=runner_calls,
            control_read_calls=control_read_calls,
            sleep_calls=sleep_calls,
            public_event_calls=public_event_calls,
            preflight_ready=preflight_ready,
            manual_removal_confirmed=manual_removal_confirmed,
            second_confirmation_confirmed=second_confirmation_confirmed,
            attention_boundary_reached=attention_boundary_reached,
            roundtrip_calls=roundtrip_calls,
            same_private_outcome_handed_off=same_private_outcome_handed_off,
            waiting_state_consumed=waiting_state_consumed,
            command_close_verified=command_close_verified,
            maximum_lifetime_seconds=self._lifetime_seconds,
            poll_interval_seconds=self._poll_seconds,
        )

    def preview(self) -> M86LifecycleRunnerSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86g_lifecycle_runner_inert",
            execution_requested=False,
        )

    async def run_once(
        self,
        *,
        execute: bool = False,
        first_confirmation: Optional[str] = None,
    ) -> M86LifecycleRunnerSnapshot:
        if not execute:
            return self.preview()
        if not self._execution_enabled:
            return self._snapshot(
                state="NO-GO",
                reason="m86g_execution_not_enabled",
                execution_requested=True,
            )
        if self._used or self._command is None:
            self._used = True
            return self._snapshot(
                state="NO-GO",
                reason="m86g_runner_reuse_rejected",
                execution_requested=True,
            )
        self._used = True

        counters = {
            "control": 0,
            "sleep": 0,
            "events": 0,
            "roundtrip": 0,
        }
        flags = {
            "preflight": False,
            "manual": False,
            "second": False,
            "attention": False,
            "same_outcome": False,
            "consumed": False,
        }
        terminal_state = "NO-GO"
        terminal_reason = "m86g_lifecycle_failed_safe"
        command_close_verified = False
        try:
            terminal_state, terminal_reason = await asyncio.wait_for(
                self._run_lifecycle(
                    first_confirmation=first_confirmation,
                    counters=counters,
                    flags=flags,
                ),
                timeout=self._lifetime_seconds,
            )
        except asyncio.TimeoutError:
            terminal_state = "TIMED-OUT"
            terminal_reason = "m86g_lifetime_expired"
        except asyncio.CancelledError:
            terminal_state = "CANCELLED"
            terminal_reason = "m86g_lifecycle_cancelled"
        except BaseException:
            terminal_state = "NO-GO"
            terminal_reason = "m86g_lifecycle_failed_safe"
        finally:
            command, self._command = self._command, None
            if command is not None:
                try:
                    closed = await command.close()
                    command_close_verified = closed.state == "CLOSED"
                except BaseException:
                    command_close_verified = False
            self._control_reader = None
            self._channel_factory = None
            self._event_sink = None
            self._roundtrip = None
            self._sleeper = None

        if not command_close_verified:
            terminal_state = "NO-GO"
            terminal_reason = "m86g_terminal_cleanup_failed"
        return self._snapshot(
            state=terminal_state,
            reason=terminal_reason,
            execution_requested=True,
            runner_calls=1,
            control_read_calls=counters["control"],
            sleep_calls=counters["sleep"],
            public_event_calls=counters["events"],
            preflight_ready=flags["preflight"],
            manual_removal_confirmed=flags["manual"],
            second_confirmation_confirmed=flags["second"],
            attention_boundary_reached=flags["attention"],
            roundtrip_calls=counters["roundtrip"],
            same_private_outcome_handed_off=flags["same_outcome"],
            waiting_state_consumed=flags["consumed"],
            command_close_verified=command_close_verified,
        )

    async def _run_lifecycle(self, *, first_confirmation, counters, flags):
        command = self._command
        control_reader = self._control_reader
        channel_factory = self._channel_factory
        event_sink = self._event_sink
        roundtrip = self._roundtrip
        sleeper = self._sleeper
        if None in (
            command,
            control_reader,
            channel_factory,
            event_sink,
            roundtrip,
            sleeper,
        ):
            raise RuntimeError("m86g_dependencies_consumed")

        preflight = await command.run_once(
            execute=True,
            first_confirmation=first_confirmation,
        )
        if (
            preflight.state != "PREFLIGHT-READY"
            or not preflight.private_anchor_retained
            or preflight.channel_stage
            is not M86ChannelStage.AWAITING_MANUAL_REMOVAL
        ):
            raise RuntimeError("m86g_preflight_not_ready")
        outcome = command.take_private_history_outcome_once()
        flags["preflight"] = True
        await self._emit(
            event_sink,
            counters,
            state="PREFLIGHT-READY",
            sequence=1,
            attention=False,
        )

        manual_event_emitted = False
        while True:
            counters["control"] += 1
            record = await control_reader()
            if type(record) is not M86ChannelRecord:
                raise RuntimeError("m86g_control_record_invalid")
            if record.stage is M86ChannelStage.AWAITING_MANUAL_REMOVAL:
                counters["sleep"] += 1
                await sleeper(self._poll_seconds)
                continue
            if record.stage is M86ChannelStage.AWAITING_SECOND_CONFIRMATION:
                flags["manual"] = True
                if not manual_event_emitted:
                    await self._emit(
                        event_sink,
                        counters,
                        state="MANUAL-REMOVAL-CONFIRMED",
                        sequence=2,
                        attention=False,
                    )
                    manual_event_emitted = True
                counters["sleep"] += 1
                await sleeper(self._poll_seconds)
                continue
            if record.stage is M86ChannelStage.READY_FOR_WAITING_MESSAGE:
                flags["manual"] = True
                flags["second"] = True
                if not manual_event_emitted:
                    await self._emit(
                        event_sink,
                        counters,
                        state="MANUAL-REMOVAL-CONFIRMED",
                        sequence=2,
                        attention=False,
                    )
                await self._emit(
                    event_sink,
                    counters,
                    state="SECOND-CONFIRMATION-CONFIRMED",
                    sequence=3,
                    attention=False,
                )
                waiting = channel_factory().advance_once(
                    action=M86ChannelAction.MARK_WAITING_MESSAGE,
                )
                if waiting.state != "ATTENTION-REQUIRED":
                    raise RuntimeError("m86g_attention_transition_failed")
                flags["attention"] = True
                await self._emit(
                    event_sink,
                    counters,
                    state="ATTENTION-REQUIRED",
                    sequence=4,
                    attention=True,
                )
                counters["roundtrip"] = 1
                result = await roundtrip(outcome)
                flags["same_outcome"] = True
                result_state = getattr(result, "state", None)
                if result_state not in ("VERIFIED", "ROLLED-BACK"):
                    raise RuntimeError("m86g_roundtrip_result_invalid")
                consumed = channel_factory().advance_once(
                    action=M86ChannelAction.CONSUME_WAITING_MESSAGE,
                )
                if consumed.state != "CONSUMED" or not consumed.private_state_cleared:
                    raise RuntimeError("m86g_waiting_cleanup_failed")
                flags["consumed"] = True
                return (
                    result_state,
                    "m86g_lifecycle_verified"
                    if result_state == "VERIFIED"
                    else "m86g_lifecycle_rolled_back",
                )
            raise RuntimeError("m86g_control_stage_invalid")

    @staticmethod
    async def _emit(sink, counters, *, state, sequence, attention):
        await sink(
            M86LifecyclePublicEvent(
                phase="M86-G",
                state=state,
                sequence=sequence,
                attention_required_now=attention,
                human_message_required_now=attention,
            )
        )
        counters["events"] += 1


async def _real_control_reader() -> Optional[M86ChannelRecord]:
    root = Path(__file__).resolve().parent.parent / ".runtime"
    return JsonFileM86AllowlistedStateBackend(root=root).load()


def _real_channel_factory() -> M86CrossTurnChannel:
    root = Path(__file__).resolve().parent.parent / ".runtime"
    return M86CrossTurnChannel(
        backend=JsonFileM86AllowlistedStateBackend(root=root),
        execution_enabled=True,
    )


async def _unbound_real_event_sink(_event: M86LifecyclePublicEvent) -> None:
    raise RuntimeError("m86g_real_status_surface_unbound")


async def _unbound_real_roundtrip(_outcome: object) -> object:
    raise RuntimeError("m86g_real_m88_continuation_unbound")


def build_real_m86_lifecycle_runner() -> M86LifecycleRunner:
    """Builder real inerte: no crea runtime, fuente, HTTP ni proceso."""

    return M86LifecycleRunner(
        command=build_real_m86_source_bound_command(),
        control_reader=_real_control_reader,
        channel_factory=_real_channel_factory,
        event_sink=_unbound_real_event_sink,
        roundtrip_continuation=_unbound_real_roundtrip,
        execution_enabled=False,
    )


__all__ = [
    "M86G_DEFAULT_POLL_SECONDS",
    "M86G_MAX_LIFETIME_SECONDS",
    "M86LifecyclePublicEvent",
    "M86LifecycleRunner",
    "M86LifecycleRunnerSnapshot",
    "build_real_m86_lifecycle_runner",
]
