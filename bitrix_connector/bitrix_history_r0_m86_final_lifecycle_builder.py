"""M86-J: builder final inerte del ciclo protegido M86-H/I/G."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
)
from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthBackend,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_m85_final_command_rehearsal import (
    M85_FIRST_CONFIRMATION_TEXT,
)
from .bitrix_history_r0_m86_concrete_lifecycle_operations import (
    AsyncClientFactory,
    M86ConcreteLifecycleOperations,
)
from .bitrix_history_r0_m86_cross_turn_channel import (
    JsonFileM86AllowlistedStateBackend,
    M86ChannelAction,
    M86ChannelRecord,
    M86ChannelStage,
    M86CrossTurnChannel,
)
from .bitrix_history_r0_m86_lifecycle_runner import M86LifecyclePublicEvent
from .bitrix_history_r0_m86_protected_lifecycle_resources import (
    M86ProtectedLifecycleResourceOwner,
)
from .bitrix_history_r0_m86_real_https_factory import (
    build_real_m86_https_async_client,
)
from .bitrix_history_r0_m86_stored_oauth_backend import (
    build_real_m86_stored_oauth_backend,
)
from .bitrix_history_r0_protected_helper import ProtectedFailureCategory
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
)
from .config import load_settings


M86J_MAX_LIFETIME_SECONDS = 300.0
M86J_DEFAULT_POLL_SECONDS = 0.25

ControlReader = Callable[[], Awaitable[Optional[M86ChannelRecord]]]
ChannelFactory = Callable[[], M86CrossTurnChannel]
PublicEventSink = Callable[[M86LifecyclePublicEvent], Awaitable[None]]
MessageReadyWaiter = Callable[[], Awaitable[bool]]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class M86LifecycleSurfaceSnapshot:
    phase: Literal["M86-L"]
    state: Literal[
        "PREPARED",
        "PREFLIGHT-READY",
        "MANUAL-REMOVAL-CONFIRMED",
        "SECOND-CONFIRMATION-CONFIRMED",
        "ATTENTION-REQUIRED",
        "MESSAGE-SENT-CONFIRMED",
        "NO-GO",
    ]
    sequence: int
    event_calls: int
    signal_calls: int
    attention_required_now: bool
    human_message_required_now: bool
    message_sent_confirmed: bool
    allowlisted_fields_only: Literal[True] = True
    payload_retained: Literal[False] = False
    retry_budget: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86AllowlistedLifecycleSurface:
    """Superficie allowlisted compartible para estado y señal humana one-shot."""

    _EVENT_STATES = (
        "PREFLIGHT-READY",
        "MANUAL-REMOVAL-CONFIRMED",
        "SECOND-CONFIRMATION-CONFIRMED",
        "ATTENTION-REQUIRED",
    )

    def __init__(
        self,
        *,
        control_reader: ControlReader,
        channel_factory: ChannelFactory,
        sleeper: Sleeper = asyncio.sleep,
        poll_seconds: float = M86J_DEFAULT_POLL_SECONDS,
        observer: Optional[PublicEventSink] = None,
    ) -> None:
        if (
            not callable(control_reader)
            or not callable(channel_factory)
            or not callable(sleeper)
            or type(poll_seconds) not in (int, float)
            or poll_seconds <= 0
            or poll_seconds > 5
            or (observer is not None and not callable(observer))
        ):
            raise TypeError("m86l_surface_observer_invalid")
        self._control_reader = control_reader
        self._channel_factory = channel_factory
        self._sleeper = sleeper
        self._poll_seconds = float(poll_seconds)
        self._observer: Optional[PublicEventSink] = observer
        self._state = "PREPARED"
        self._sequence = 0
        self._event_calls = 0
        self._signal_calls = 0
        self._failed = False

    def __repr__(self) -> str:
        return "M86AllowlistedLifecycleSurface(<redacted>)"

    async def publish(self, event: M86LifecyclePublicEvent) -> None:
        if (
            self._failed
            or type(event) is not M86LifecyclePublicEvent
            or self._event_calls >= len(self._EVENT_STATES)
            or event.state != self._EVENT_STATES[self._event_calls]
            or event.sequence != self._event_calls + 1
            or event.attention_required_now
            != (event.state == "ATTENTION-REQUIRED")
            or event.human_message_required_now != event.attention_required_now
        ):
            self._failed = True
            raise RuntimeError("m86l_surface_event_invalid")
        self._event_calls += 1
        self._state = event.state
        self._sequence = event.sequence
        if self._observer is not None:
            await self._observer(event)

    async def wait_message_sent(self) -> bool:
        if self._failed or self._state not in (
            "ATTENTION-REQUIRED",
            "MESSAGE-SENT-CONFIRMED",
        ):
            raise RuntimeError("m86l_surface_wait_invalid")
        for _ in range(int(M86J_MAX_LIFETIME_SECONDS / self._poll_seconds) + 1):
            record = await self._control_reader()
            if type(record) is not M86ChannelRecord:
                raise RuntimeError("m86l_surface_record_invalid")
            if record.stage is M86ChannelStage.MESSAGE_SENT:
                self._signal_calls = 1
                self._state = "MESSAGE-SENT-CONFIRMED"
                return True
            if record.stage is not M86ChannelStage.WAITING_MESSAGE:
                raise RuntimeError("m86l_surface_stage_invalid")
            await self._sleeper(self._poll_seconds)
        raise RuntimeError("m86l_surface_signal_timeout")

    def confirm_message_sent_once(self) -> M86LifecycleSurfaceSnapshot:
        if self._failed or self._signal_calls != 0:
            self._failed = True
            return self._snapshot("NO-GO")
        result = self._channel_factory().advance_once(
            action=M86ChannelAction.CONFIRM_MESSAGE_SENT
        )
        if (
            result.state != "ADVANCED"
            or result.resulting_stage is not M86ChannelStage.MESSAGE_SENT
            or result.sequence != 5
        ):
            self._failed = True
            return self._snapshot("NO-GO")
        self._signal_calls = 1
        self._state = "MESSAGE-SENT-CONFIRMED"
        self._sequence = 5
        return self.snapshot()

    async def refresh_status(self) -> M86LifecycleSurfaceSnapshot:
        record = await self._control_reader()
        if record is None:
            return self.snapshot()
        self._sequence = record.sequence
        self._state = {
            M86ChannelStage.AWAITING_MANUAL_REMOVAL: "PREFLIGHT-READY",
            M86ChannelStage.AWAITING_SECOND_CONFIRMATION: (
                "MANUAL-REMOVAL-CONFIRMED"
            ),
            M86ChannelStage.READY_FOR_WAITING_MESSAGE: (
                "SECOND-CONFIRMATION-CONFIRMED"
            ),
            M86ChannelStage.WAITING_MESSAGE: "ATTENTION-REQUIRED",
            M86ChannelStage.MESSAGE_SENT: "MESSAGE-SENT-CONFIRMED",
        }[record.stage]
        if record.stage is M86ChannelStage.MESSAGE_SENT:
            self._signal_calls = 1
        return self.snapshot()

    def snapshot(self) -> M86LifecycleSurfaceSnapshot:
        return self._snapshot("NO-GO" if self._failed else self._state)

    def _snapshot(self, state: str) -> M86LifecycleSurfaceSnapshot:
        attention = state == "ATTENTION-REQUIRED"
        return M86LifecycleSurfaceSnapshot(
            phase="M86-L",
            state=state,
            sequence=self._sequence,
            event_calls=self._event_calls,
            signal_calls=self._signal_calls,
            attention_required_now=attention,
            human_message_required_now=attention,
            message_sent_confirmed=(
                state == "MESSAGE-SENT-CONFIRMED" and self._signal_calls == 1
            ),
        )


class _M86ProtectedCrossTurnWaiter:
    """Reutiliza la secuencia G y pausa después de pedir atención."""

    def __init__(
        self,
        *,
        control_reader: ControlReader,
        channel_factory: ChannelFactory,
        event_sink: PublicEventSink,
        message_ready_waiter: MessageReadyWaiter,
        sleeper: Sleeper,
        poll_seconds: float,
    ) -> None:
        self._control_reader: Optional[ControlReader] = control_reader
        self._channel_factory: Optional[ChannelFactory] = channel_factory
        self._event_sink: Optional[PublicEventSink] = event_sink
        self._message_ready_waiter: Optional[MessageReadyWaiter] = (
            message_ready_waiter
        )
        self._sleeper: Optional[Sleeper] = sleeper
        self._poll_seconds = poll_seconds
        self.calls = 0
        self.control_reads = 0
        self.sleep_calls = 0
        self.public_events = 0
        self.message_ready_waits = 0
        self.attention_events = 0
        self.waiting_reached = False

    async def __call__(self, _settings, _token_view, _outcome) -> None:
        dependencies = (
            self._control_reader,
            self._channel_factory,
            self._event_sink,
            self._message_ready_waiter,
            self._sleeper,
        )
        if self.calls != 0 or any(item is None for item in dependencies):
            raise RuntimeError("m86j_cross_turn_reuse_or_dependency_invalid")
        self.calls = 1
        control_reader, channel_factory, event_sink, message_waiter, sleeper = (
            dependencies
        )
        self._control_reader = None
        self._event_sink = None
        self._message_ready_waiter = None
        self._sleeper = None

        opened = channel_factory().advance_once(
            action=M86ChannelAction.OPEN_AFTER_PREFLIGHT
        )
        if (
            opened.state != "ADVANCED"
            or opened.resulting_stage is not M86ChannelStage.AWAITING_MANUAL_REMOVAL
        ):
            raise RuntimeError("m86j_channel_open_failed")
        await self._emit(event_sink, "PREFLIGHT-READY", 1, False)

        manual_emitted = False
        for _ in range(int(M86J_MAX_LIFETIME_SECONDS / self._poll_seconds) + 1):
            self.control_reads += 1
            record = await control_reader()
            if type(record) is not M86ChannelRecord:
                raise RuntimeError("m86j_control_record_invalid")
            if record.stage is M86ChannelStage.AWAITING_MANUAL_REMOVAL:
                self.sleep_calls += 1
                await sleeper(self._poll_seconds)
                continue
            if record.stage is M86ChannelStage.AWAITING_SECOND_CONFIRMATION:
                if not manual_emitted:
                    await self._emit(
                        event_sink, "MANUAL-REMOVAL-CONFIRMED", 2, False
                    )
                    manual_emitted = True
                self.sleep_calls += 1
                await sleeper(self._poll_seconds)
                continue
            if record.stage is M86ChannelStage.READY_FOR_WAITING_MESSAGE:
                if not manual_emitted:
                    await self._emit(
                        event_sink, "MANUAL-REMOVAL-CONFIRMED", 2, False
                    )
                await self._emit(
                    event_sink, "SECOND-CONFIRMATION-CONFIRMED", 3, False
                )
                waiting = channel_factory().advance_once(
                    action=M86ChannelAction.MARK_WAITING_MESSAGE
                )
                if waiting.state != "ATTENTION-REQUIRED":
                    raise RuntimeError("m86j_attention_transition_failed")
                self.waiting_reached = True
                await self._emit(event_sink, "ATTENTION-REQUIRED", 4, True)
                self.attention_events = 1
                self.message_ready_waits = 1
                if await message_waiter() is not True:
                    raise RuntimeError("m86j_message_ready_not_confirmed")
                return
            raise RuntimeError("m86j_control_stage_invalid")
        raise RuntimeError("m86j_cross_turn_poll_budget_exhausted")

    async def _emit(self, sink, state, sequence, attention) -> None:
        await sink(
            M86LifecyclePublicEvent(
                phase="M86-G",
                state=state,
                sequence=sequence,
                attention_required_now=attention,
                human_message_required_now=attention,
            )
        )
        self.public_events += 1

    def clear(self) -> None:
        self._control_reader = None
        self._channel_factory = None
        self._event_sink = None
        self._message_ready_waiter = None
        self._sleeper = None


@dataclass(frozen=True)
class M86FinalLifecycleSnapshot:
    phase: Literal["M86-J"]
    state: Literal["PREPARED", "VERIFIED", "ROLLED-BACK", "NO-GO"]
    reason: str
    execution_requested: bool
    first_confirmation_exact: bool
    protected_scope_bound: Literal[True]
    concrete_operations_bound: Literal[True]
    cross_turn_wait_bound: Literal[True]
    public_status_surface_bound: Literal[True]
    launch_surface_available: Literal[True]
    status_surface_available: Literal[True]
    message_signal_surface_available: Literal[True]
    sender_scope_mode: Literal["controlled_chat_exact_unique_message"]
    expected_sender_id_required: Literal[False]
    owner_calls: int
    preflight_calls: int
    cross_turn_calls: int
    m88_calls: int
    public_event_calls: int
    attention_event_calls: int
    message_ready_wait_calls: int
    channel_cleanup_calls: int
    channel_cleanup_verified: bool
    private_resources_closed: bool
    same_oauth_view_used: bool
    oauth_load_calls: int
    oauth_refresh_calls: Literal[0]
    protected_failure_category: ProtectedFailureCategory
    retry_budget: Literal[0] = 0
    default_execution_enabled: Literal[False] = False
    first_confirmation_decision: Literal["REQUEST"] = "REQUEST"
    first_confirmation_request_ready: Literal[True] = True
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    command_available: Literal[True] = True
    real_execution_authorized: Literal[False] = False
    remaining_real_bindings: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86FinalLifecycleOwner:
    """Compone M86-H/I/G; sólo una ejecución explícitamente habilitada avanza."""

    def __init__(
        self,
        *,
        credential_backend: InjectedWindowsCredentialBackend,
        oauth_backend: InjectedStoredOAuthBackend,
        nia_base_url: str,
        http_client_factory: AsyncClientFactory,
        control_reader: ControlReader,
        channel_factory: ChannelFactory,
        expected_sender_id: Optional[int] = None,
        status_surface: Optional[M86AllowlistedLifecycleSurface] = None,
        settings_loader: ProtectedSettingsLoader = load_settings,
        sleeper: Sleeper = asyncio.sleep,
        poll_seconds: float = M86J_DEFAULT_POLL_SECONDS,
        execution_enabled: bool = False,
        emergency_rollback: bool = False,
    ) -> None:
        callbacks = (
            http_client_factory,
            control_reader,
            channel_factory,
            settings_loader,
            sleeper,
        )
        if (
            credential_backend is None
            or oauth_backend is None
            or any(not callable(item) for item in callbacks)
            or type(execution_enabled) is not bool
            or type(poll_seconds) not in (int, float)
            or poll_seconds <= 0
            or poll_seconds > 5
        ):
            raise TypeError("m86j_owner_dependency_invalid")
        self._channel_factory: Optional[ChannelFactory] = channel_factory
        self._surface = status_surface or M86AllowlistedLifecycleSurface(
            control_reader=control_reader,
            channel_factory=channel_factory,
            sleeper=sleeper,
            poll_seconds=float(poll_seconds),
        )
        if type(self._surface) is not M86AllowlistedLifecycleSurface:
            raise TypeError("m86j_status_surface_invalid")
        self._waiter = _M86ProtectedCrossTurnWaiter(
            control_reader=control_reader,
            channel_factory=channel_factory,
            event_sink=self._surface.publish,
            message_ready_waiter=self._surface.wait_message_sent,
            sleeper=sleeper,
            poll_seconds=float(poll_seconds),
        )
        operations = M86ConcreteLifecycleOperations(
            nia_base_url=nia_base_url,
            http_client_factory=http_client_factory,
            cross_turn_waiter=self._waiter,
            expected_sender_id=expected_sender_id,
            emergency_rollback=emergency_rollback,
        )
        self._resources: Optional[M86ProtectedLifecycleResourceOwner] = (
            M86ProtectedLifecycleResourceOwner(
                credential_backend=credential_backend,
                oauth_backend=oauth_backend,
                preflight_operation=operations.preflight,
                cross_turn_operation=operations.cross_turn,
                m88_operation=operations.m88,
                settings_loader=settings_loader,
                execution_enabled=execution_enabled,
            )
        )
        self._execution_enabled = execution_enabled
        self._used = False

    def __repr__(self) -> str:
        return "M86FinalLifecycleOwner(<redacted>)"

    def _snapshot(self, *, state, reason, execution_requested, **values):
        defaults = {
            "first_confirmation_exact": False,
            "owner_calls": 0,
            "preflight_calls": 0,
            "cross_turn_calls": 0,
            "m88_calls": 0,
            "public_event_calls": 0,
            "attention_event_calls": 0,
            "message_ready_wait_calls": 0,
            "channel_cleanup_calls": 0,
            "channel_cleanup_verified": True,
            "private_resources_closed": True,
            "same_oauth_view_used": False,
            "oauth_load_calls": 0,
            "protected_failure_category": "none",
        }
        defaults.update(values)
        return M86FinalLifecycleSnapshot(
            phase="M86-J",
            state=state,
            reason=reason,
            execution_requested=execution_requested,
            protected_scope_bound=True,
            concrete_operations_bound=True,
            cross_turn_wait_bound=True,
            public_status_surface_bound=True,
            launch_surface_available=True,
            status_surface_available=True,
            message_signal_surface_available=True,
            sender_scope_mode="controlled_chat_exact_unique_message",
            expected_sender_id_required=False,
            oauth_refresh_calls=0,
            **defaults,
        )

    def preview(self) -> M86FinalLifecycleSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86j_final_lifecycle_builder_inert",
            execution_requested=False,
        )

    def status(self) -> M86LifecycleSurfaceSnapshot:
        return self._surface.snapshot()

    def confirm_message_sent_once(self) -> M86LifecycleSurfaceSnapshot:
        return self._surface.confirm_message_sent_once()

    async def run_once(
        self,
        *,
        execute: bool = False,
        first_confirmation: Optional[str] = None,
    ) -> M86FinalLifecycleSnapshot:
        if not execute:
            return self.preview()
        if not self._execution_enabled:
            return self._snapshot(
                state="NO-GO",
                reason="m86j_execution_not_enabled",
                execution_requested=True,
            )
        if self._used or self._resources is None:
            self._used = True
            return self._snapshot(
                state="NO-GO",
                reason="m86j_owner_reuse_rejected",
                execution_requested=True,
            )
        self._used = True
        if first_confirmation != M85_FIRST_CONFIRMATION_TEXT:
            await self._cleanup_channel(success=False)
            return self._snapshot(
                state="NO-GO",
                reason="m86j_first_confirmation_invalid",
                execution_requested=True,
                channel_cleanup_calls=1,
            )

        resources, self._resources = self._resources, None
        result = await resources.run_once(execute=True)
        successful = result.state in ("VERIFIED", "ROLLED-BACK")
        cleanup_verified = await self._cleanup_channel(success=successful)
        state = result.state if successful and cleanup_verified else "NO-GO"
        return self._snapshot(
            state=state,
            reason=(
                "m86j_final_lifecycle_verified"
                if state == "VERIFIED"
                else "m86j_final_lifecycle_rolled_back"
                if state == "ROLLED-BACK"
                else "m86j_final_lifecycle_failed_safe"
            ),
            execution_requested=True,
            first_confirmation_exact=True,
            owner_calls=1,
            preflight_calls=result.preflight_calls,
            cross_turn_calls=result.cross_turn_calls,
            m88_calls=result.m88_calls,
            public_event_calls=self._waiter.public_events,
            attention_event_calls=self._waiter.attention_events,
            message_ready_wait_calls=self._waiter.message_ready_waits,
            channel_cleanup_calls=1,
            channel_cleanup_verified=cleanup_verified,
            private_resources_closed=result.private_resources_closed,
            same_oauth_view_used=result.same_oauth_view_used,
            oauth_load_calls=result.oauth_load_calls,
            protected_failure_category=result.protected_failure_category,
        )

    async def _cleanup_channel(self, *, success: bool) -> bool:
        factory, self._channel_factory = self._channel_factory, None
        self._waiter.clear()
        if factory is None:
            return False
        try:
            action = (
                M86ChannelAction.CONSUME_WAITING_MESSAGE
                if success and self._waiter.waiting_reached
                else M86ChannelAction.ABORT
            )
            result = factory().advance_once(action=action)
            return result.state == "CONSUMED" and result.private_state_cleared
        except BaseException:
            return False


def _build_real_m86_channel_bindings() -> tuple[ControlReader, ChannelFactory]:
    runtime_root = Path(__file__).resolve().parent.parent / ".runtime"

    def channel_factory() -> M86CrossTurnChannel:
        return M86CrossTurnChannel(
            backend=JsonFileM86AllowlistedStateBackend(root=runtime_root),
            execution_enabled=True,
        )

    async def control_reader() -> Optional[M86ChannelRecord]:
        return JsonFileM86AllowlistedStateBackend(root=runtime_root).load()

    return control_reader, channel_factory


def build_real_m86_lifecycle_surface() -> M86AllowlistedLifecycleSurface:
    """Enlaza estado/señal compartidos sin crear ni abrir `.runtime`."""

    control_reader, channel_factory = _build_real_m86_channel_bindings()
    return M86AllowlistedLifecycleSurface(
        control_reader=control_reader,
        channel_factory=channel_factory,
    )


def build_real_m86_final_lifecycle_owner(
    *,
    nia_base_url: str,
    expected_sender_id: Optional[int] = None,
    execution_enabled: bool = False,
) -> M86FinalLifecycleOwner:
    """Compone referencias reales sin abrir fuente, HTTP o `.runtime`."""

    control_reader, channel_factory = _build_real_m86_channel_bindings()

    return M86FinalLifecycleOwner(
        credential_backend=build_real_windows_credential_backend(),
        oauth_backend=build_real_m86_stored_oauth_backend(),
        nia_base_url=nia_base_url,
        http_client_factory=build_real_m86_https_async_client,
        control_reader=control_reader,
        channel_factory=channel_factory,
        expected_sender_id=expected_sender_id,
        execution_enabled=execution_enabled,
    )


__all__ = [
    "M86AllowlistedLifecycleSurface",
    "M86FinalLifecycleOwner",
    "M86FinalLifecycleSnapshot",
    "M86LifecycleSurfaceSnapshot",
    "M86J_DEFAULT_POLL_SECONDS",
    "M86J_MAX_LIFETIME_SECONDS",
    "build_real_m86_final_lifecycle_owner",
    "build_real_m86_lifecycle_surface",
]
