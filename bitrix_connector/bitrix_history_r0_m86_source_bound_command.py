"""M86-E: comando source-bound, perezoso y bloqueado por confirmación exacta."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional, Protocol

from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_m85_final_command_rehearsal import (
    M85_FIRST_CONFIRMATION_TEXT,
)
from .bitrix_history_r0_m86_combined_preflight_owner import (
    M86CombinedPreflightOwner,
)
from .bitrix_history_r0_m86_cross_turn_channel import (
    JsonFileM86AllowlistedStateBackend,
    M86ChannelAction,
    M86ChannelStage,
    M86CrossTurnChannel,
)
from .bitrix_history_r0_m86_real_https_factory import (
    build_real_m86_https_async_client,
)
from .bitrix_history_r0_m86_stored_oauth_backend import (
    build_real_m86_stored_oauth_backend,
)


M86E_COMMAND_NAME = "nia-next-r1-first-confirmation-preflight"
M86E_MAX_TIMEOUT_SECONDS = 300.0


class M86EPreflightOwner(Protocol):
    async def run_once(self): ...

    def take_history_outcome_once(self): ...

    def clear(self) -> None: ...


PreflightOwnerFactory = Callable[[], M86EPreflightOwner]
ChannelFactory = Callable[[], M86CrossTurnChannel]


@dataclass(frozen=True)
class M86SourceBoundCommandSnapshot:
    phase: Literal["M86-E"]
    state: Literal[
        "PREPARED",
        "PREFLIGHT-READY",
        "NO-GO",
        "CANCELLED",
        "CLOSED",
    ]
    reason: str
    execution_requested: bool
    first_confirmation_exact: bool
    first_confirmation_consumed: bool
    preflight_owner_factory_calls: int
    preflight_owner_calls: int
    channel_factory_calls: int
    channel_action_calls: int
    preflight_read_calls: int
    combined_preflight_verified: bool
    private_anchor_retained: bool
    private_anchor_persisted: Literal[False] = False
    channel_stage: Optional[M86ChannelStage] = None
    two_confirmations_separate: Literal[True] = True
    first_confirmation_decision: Literal["REQUEST"] = "REQUEST"
    first_confirmation_request_ready: Literal[True] = True
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    source_bound: Literal[True] = True
    command_available: Literal[True] = True
    cli_available: Literal[False] = False
    default_execution_enabled: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    retry_budget: Literal[0] = 0
    remaining_real_bindings: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86SourceBoundCommand:
    """Owner one-shot; conserva el outcome privado sólo mientras siga vivo."""

    __slots__ = (
        "_channel_factory",
        "_execution_enabled",
        "_history_outcome",
        "_preflight_owner",
        "_preflight_owner_factory",
        "_timeout_seconds",
        "_used",
    )

    def __init__(
        self,
        *,
        preflight_owner_factory: PreflightOwnerFactory,
        channel_factory: ChannelFactory,
        execution_enabled: bool = False,
        timeout_seconds: float = M86E_MAX_TIMEOUT_SECONDS,
    ) -> None:
        if (
            not callable(preflight_owner_factory)
            or not callable(channel_factory)
            or type(execution_enabled) is not bool
            or type(timeout_seconds) not in (int, float)
            or timeout_seconds <= 0
            or timeout_seconds > M86E_MAX_TIMEOUT_SECONDS
        ):
            raise TypeError("m86e_command_dependency_invalid")
        self._preflight_owner_factory: Optional[PreflightOwnerFactory] = (
            preflight_owner_factory
        )
        self._channel_factory: Optional[ChannelFactory] = channel_factory
        self._execution_enabled = execution_enabled
        self._timeout_seconds = float(timeout_seconds)
        self._preflight_owner: Optional[M86EPreflightOwner] = None
        self._history_outcome: Optional[object] = None
        self._used = False

    def __repr__(self) -> str:
        return "M86SourceBoundCommand(<redacted>)"

    @staticmethod
    def _snapshot(
        *,
        state: str,
        reason: str,
        execution_requested: bool,
        first_confirmation_exact: bool = False,
        first_confirmation_consumed: bool = False,
        preflight_owner_factory_calls: int = 0,
        preflight_owner_calls: int = 0,
        channel_factory_calls: int = 0,
        channel_action_calls: int = 0,
        preflight_read_calls: int = 0,
        combined_preflight_verified: bool = False,
        private_anchor_retained: bool = False,
        channel_stage: Optional[M86ChannelStage] = None,
    ) -> M86SourceBoundCommandSnapshot:
        return M86SourceBoundCommandSnapshot(
            phase="M86-E",
            state=state,
            reason=reason,
            execution_requested=execution_requested,
            first_confirmation_exact=first_confirmation_exact,
            first_confirmation_consumed=first_confirmation_consumed,
            preflight_owner_factory_calls=preflight_owner_factory_calls,
            preflight_owner_calls=preflight_owner_calls,
            channel_factory_calls=channel_factory_calls,
            channel_action_calls=channel_action_calls,
            preflight_read_calls=preflight_read_calls,
            combined_preflight_verified=combined_preflight_verified,
            private_anchor_retained=private_anchor_retained,
            channel_stage=channel_stage,
        )

    def preview(self) -> M86SourceBoundCommandSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86e_source_bound_command_inert_ready_for_first_confirmation",
            execution_requested=False,
        )

    async def run_once(
        self,
        *,
        execute: bool = False,
        first_confirmation: Optional[str] = None,
    ) -> M86SourceBoundCommandSnapshot:
        if not execute:
            return self.preview()
        if not self._execution_enabled:
            return self._snapshot(
                state="NO-GO",
                reason="m86e_execution_not_enabled",
                execution_requested=True,
            )
        if self._used or self._preflight_owner_factory is None:
            self._used = True
            return self._snapshot(
                state="NO-GO",
                reason="m86e_command_reuse_rejected",
                execution_requested=True,
            )
        self._used = True
        if type(first_confirmation) is not str or first_confirmation != M85_FIRST_CONFIRMATION_TEXT:
            self._preflight_owner_factory = None
            self._channel_factory = None
            return self._snapshot(
                state="NO-GO",
                reason="m86e_first_confirmation_invalid",
                execution_requested=True,
            )

        first_confirmation = None
        preflight_factory, self._preflight_owner_factory = (
            self._preflight_owner_factory,
            None,
        )
        channel_factory = self._channel_factory
        preflight_factory_calls = 0
        preflight_calls = 0
        channel_factory_calls = 0
        channel_calls = 0
        try:
            preflight_factory_calls = 1
            preflight = preflight_factory()
            if not all(
                callable(getattr(preflight, name, None))
                for name in ("run_once", "take_history_outcome_once", "clear")
            ):
                raise TypeError("m86e_preflight_owner_invalid")
            self._preflight_owner = preflight
            preflight_calls = 1
            preflight_snapshot = await asyncio.wait_for(
                preflight.run_once(),
                timeout=self._timeout_seconds,
            )
            if (
                getattr(preflight_snapshot, "state", None) != "VERIFIED"
                or getattr(preflight_snapshot, "combined_preflight_verified", None)
                is not True
                or getattr(preflight_snapshot, "history_anchor_available", None)
                is not True
                or getattr(preflight_snapshot, "private_resources_closed", None)
                is not True
                or getattr(preflight_snapshot, "bot_read_calls", None) != 2
                or getattr(preflight_snapshot, "openline_read_calls", None) != 1
                or getattr(preflight_snapshot, "history_dialog_read_calls", None) != 1
                or getattr(preflight_snapshot, "history_read_calls", None) != 0
                or getattr(preflight_snapshot, "oauth_refresh_calls", None) != 0
                or getattr(preflight_snapshot, "messages_sent", None) != 0
                or getattr(preflight_snapshot, "deletions_executed", None) != 0
                or getattr(preflight_snapshot, "connector_locked_off", None) is not True
                or getattr(preflight_snapshot, "persisted", None) is not False
                or getattr(preflight_snapshot, "nia_next_called", None) is not False
                or getattr(preflight_snapshot, "bitrix_written", None) is not False
            ):
                raise RuntimeError("m86e_combined_preflight_not_verified")

            outcome = preflight.take_history_outcome_once()
            require_anchor = getattr(outcome, "require_anchor", None)
            if not callable(require_anchor) or require_anchor() is None:
                raise RuntimeError("m86e_private_anchor_unavailable")
            self._history_outcome = outcome

            if channel_factory is None:
                raise RuntimeError("m86e_channel_factory_unavailable")
            channel_factory_calls = 1
            channel = channel_factory()
            if type(channel) is not M86CrossTurnChannel:
                raise TypeError("m86e_channel_invalid")
            channel_calls = 1
            channel_snapshot = channel.advance_once(
                action=M86ChannelAction.OPEN_AFTER_PREFLIGHT,
            )
            if (
                channel_snapshot.state != "ADVANCED"
                or channel_snapshot.resulting_stage
                is not M86ChannelStage.AWAITING_MANUAL_REMOVAL
                or channel_snapshot.sequence != 1
            ):
                raise RuntimeError("m86e_channel_open_failed")

            return self._snapshot(
                state="PREFLIGHT-READY",
                reason="m86e_first_confirmation_consumed_preflight_ready",
                execution_requested=True,
                first_confirmation_exact=True,
                first_confirmation_consumed=True,
                preflight_owner_factory_calls=preflight_factory_calls,
                preflight_owner_calls=preflight_calls,
                channel_factory_calls=channel_factory_calls,
                channel_action_calls=channel_calls,
                preflight_read_calls=4,
                combined_preflight_verified=True,
                private_anchor_retained=True,
                channel_stage=M86ChannelStage.AWAITING_MANUAL_REMOVAL,
            )
        except asyncio.CancelledError:
            await self._fail_safe_cleanup(None)
            return self._snapshot(
                state="CANCELLED",
                reason="m86e_command_cancelled_and_cleaned",
                execution_requested=True,
                first_confirmation_exact=True,
                first_confirmation_consumed=True,
                preflight_owner_factory_calls=preflight_factory_calls,
                preflight_owner_calls=preflight_calls,
                channel_factory_calls=channel_factory_calls,
                channel_action_calls=channel_calls,
            )
        except BaseException:
            await self._fail_safe_cleanup(None)
            return self._snapshot(
                state="NO-GO",
                reason="m86e_command_failed_safe",
                execution_requested=True,
                first_confirmation_exact=True,
                first_confirmation_consumed=True,
                preflight_owner_factory_calls=preflight_factory_calls,
                preflight_owner_calls=preflight_calls,
                channel_factory_calls=channel_factory_calls,
                channel_action_calls=channel_calls,
            )

    async def _fail_safe_cleanup(
        self,
        channel_factory: Optional[ChannelFactory],
    ) -> bool:
        cleanup_verified = True
        self._history_outcome = None
        owner, self._preflight_owner = self._preflight_owner, None
        if owner is not None:
            try:
                owner.clear()
            except BaseException:
                cleanup_verified = False
        if channel_factory is not None:
            try:
                channel = channel_factory()
                result = channel.advance_once(action=M86ChannelAction.ABORT)
                if not result.private_state_cleared:
                    cleanup_verified = False
            except BaseException:
                cleanup_verified = False
        return cleanup_verified

    def take_private_history_outcome_once(self):
        outcome, self._history_outcome = self._history_outcome, None
        if outcome is None:
            raise RuntimeError("m86e_private_history_outcome_unavailable")
        return outcome

    async def close(self) -> M86SourceBoundCommandSnapshot:
        cleanup_verified = await self._fail_safe_cleanup(self._channel_factory)
        self._channel_factory = None
        self._preflight_owner_factory = None
        return self._snapshot(
            state="CLOSED" if cleanup_verified else "NO-GO",
            reason=(
                "m86e_command_closed_and_channel_cleared"
                if cleanup_verified
                else "m86e_command_close_cleanup_failed"
            ),
            execution_requested=False,
        )


def _build_real_executable_preflight_owner() -> M86CombinedPreflightOwner:
    return M86CombinedPreflightOwner(
        credential_backend=build_real_windows_credential_backend(),
        oauth_backend=build_real_m86_stored_oauth_backend(),
        http_client_factory=build_real_m86_https_async_client,
        hermetic_execution=True,
    )


def _build_real_executable_channel() -> M86CrossTurnChannel:
    runtime_root = Path(__file__).resolve().parent.parent / ".runtime"
    return M86CrossTurnChannel(
        backend=JsonFileM86AllowlistedStateBackend(root=runtime_root),
        execution_enabled=True,
    )


def build_real_m86_source_bound_command(
    *,
    execution_enabled: bool = False,
) -> M86SourceBoundCommand:
    """Compone M84 y M86-A/B/C/D sin construirlos hasta autorización exacta."""

    return M86SourceBoundCommand(
        preflight_owner_factory=_build_real_executable_preflight_owner,
        channel_factory=_build_real_executable_channel,
        execution_enabled=execution_enabled,
    )


__all__ = [
    "M86E_COMMAND_NAME",
    "M86E_MAX_TIMEOUT_SECONDS",
    "M86SourceBoundCommand",
    "M86SourceBoundCommandSnapshot",
    "build_real_m86_source_bound_command",
]
