"""Handoff efímero que conserva el ancla R0 sin leer historial."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from .bitrix_history_r0_preflight_composition import (
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    execute_stored_oauth_history_preflight_once,
)
from .bitrix_history_r0_runner import BitrixHistoryR0Result, BitrixHistoryR0Status
from .config import ConnectorSettings


MAX_AUTHORIZATION_WAIT_SECONDS = 300.0


class BitrixHistoryR0HandoffState(str, Enum):
    NO_GO = "NO-GO"
    WAITING_AUTHORIZATION = "WAITING-AUTHORIZATION"
    ARMED = "ARMED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class BitrixHistoryR0HandoffDecision(str, Enum):
    ARM = "ARM"
    CANCEL = "CANCEL"


class BitrixHistoryR0HandoffSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BitrixHistoryR0HandoffState
    reason: str
    preflight_ready: bool = False
    anchor_available: bool = False
    history_armed: bool = False
    dialog_read_calls: int = Field(default=0, ge=0, le=1)
    history_read_calls: int = Field(default=0, ge=0, le=0)
    mutation_calls: int = Field(default=0, ge=0, le=0)
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    resources_closed: bool = False


AuthorizationGate = Callable[[], Awaitable[BitrixHistoryR0HandoffDecision]]
PreflightExecutor = Callable[..., Awaitable[BitrixHistoryR0PreflightOutcome]]
ArmedReader = Callable[[BitrixHistoryR0Anchor], Awaitable[BitrixHistoryR0Result]]


class BitrixHistoryR0InMemoryHandoff:
    """Retiene un ancla privada hasta autorizar, cancelar o cerrar."""

    __slots__ = (
        "_anchor",
        "_dialog_read_calls",
        "_preflight_ready",
        "_reason",
        "_reader_started",
        "_resources_closed",
        "_state",
    )

    def __init__(
        self,
        *,
        state: BitrixHistoryR0HandoffState,
        reason: str,
        anchor: BitrixHistoryR0Anchor | None = None,
        preflight_ready: bool = False,
        dialog_read_calls: int = 0,
        resources_closed: bool = False,
    ) -> None:
        self._state = state
        self._reason = reason
        self._anchor = anchor
        self._preflight_ready = preflight_ready
        self._dialog_read_calls = dialog_read_calls
        self._resources_closed = resources_closed
        self._reader_started = False

    def __repr__(self) -> str:
        return "BitrixHistoryR0InMemoryHandoff(<redacted>)"

    @classmethod
    def from_preflight(
        cls,
        outcome: BitrixHistoryR0PreflightOutcome,
    ) -> "BitrixHistoryR0InMemoryHandoff":
        result = outcome.result
        if result.status is not BitrixHistoryR0Status.READY:
            return cls(
                state=BitrixHistoryR0HandoffState.NO_GO,
                reason=result.reason,
                dialog_read_calls=result.dialog_read_calls,
                resources_closed=result.resources_closed,
            )
        if not result.resources_closed:
            return cls(
                state=BitrixHistoryR0HandoffState.NO_GO,
                reason="bitrix_history_resources_close_failed",
                dialog_read_calls=result.dialog_read_calls,
                resources_closed=False,
            )
        if not outcome.anchor_available:
            return cls(
                state=BitrixHistoryR0HandoffState.NO_GO,
                reason="bitrix_history_handoff_anchor_unavailable",
                dialog_read_calls=result.dialog_read_calls,
                resources_closed=True,
            )
        try:
            anchor = outcome.require_anchor()
        except Exception:
            return cls(
                state=BitrixHistoryR0HandoffState.NO_GO,
                reason="bitrix_history_handoff_anchor_unavailable",
                dialog_read_calls=result.dialog_read_calls,
                resources_closed=result.resources_closed,
            )
        return cls(
            state=BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
            reason="bitrix_history_handoff_waiting_authorization",
            anchor=anchor,
            preflight_ready=True,
            dialog_read_calls=result.dialog_read_calls,
            resources_closed=True,
        )

    def snapshot(self) -> BitrixHistoryR0HandoffSnapshot:
        anchor_available = self._anchor is not None
        return BitrixHistoryR0HandoffSnapshot(
            state=self._state,
            reason=self._reason,
            preflight_ready=self._preflight_ready,
            anchor_available=anchor_available,
            history_armed=(
                self._state is BitrixHistoryR0HandoffState.ARMED
                and anchor_available
            ),
            dialog_read_calls=self._dialog_read_calls,
            resources_closed=self._resources_closed,
        )

    def _discard_anchor(self) -> None:
        self._anchor = None

    async def wait_for_authorization(
        self,
        *,
        authorization_gate: AuthorizationGate,
        timeout_seconds: float,
    ) -> BitrixHistoryR0HandoffSnapshot:
        if self._state is not BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION:
            return self.snapshot()
        if timeout_seconds <= 0 or timeout_seconds > MAX_AUTHORIZATION_WAIT_SECONDS:
            self._discard_anchor()
            self._state = BitrixHistoryR0HandoffState.NO_GO
            self._reason = "bitrix_history_handoff_timeout_invalid"
            return self.snapshot()
        try:
            decision = await asyncio.wait_for(
                authorization_gate(),
                timeout=timeout_seconds,
            )
        except asyncio.CancelledError:
            self._discard_anchor()
            self._state = BitrixHistoryR0HandoffState.CLOSED
            self._reason = "bitrix_history_handoff_cancelled"
            raise
        except asyncio.TimeoutError:
            self._discard_anchor()
            self._state = BitrixHistoryR0HandoffState.NO_GO
            self._reason = "bitrix_history_handoff_authorization_timeout"
            return self.snapshot()
        except Exception:
            self._discard_anchor()
            self._state = BitrixHistoryR0HandoffState.NO_GO
            self._reason = "bitrix_history_handoff_authorization_failed_safe"
            return self.snapshot()

        if decision is BitrixHistoryR0HandoffDecision.ARM:
            self._state = BitrixHistoryR0HandoffState.ARMED
            self._reason = "bitrix_history_handoff_armed"
        elif decision is BitrixHistoryR0HandoffDecision.CANCEL:
            self._discard_anchor()
            self._state = BitrixHistoryR0HandoffState.CANCELLED
            self._reason = "bitrix_history_handoff_cancelled"
        else:
            self._discard_anchor()
            self._state = BitrixHistoryR0HandoffState.NO_GO
            self._reason = "bitrix_history_handoff_decision_invalid"
        return self.snapshot()

    async def close(self) -> BitrixHistoryR0HandoffSnapshot:
        self._discard_anchor()
        self._state = BitrixHistoryR0HandoffState.CLOSED
        self._reason = "bitrix_history_handoff_closed"
        return self.snapshot()

    async def run_armed_reader_once(
        self,
        reader: ArmedReader,
    ) -> BitrixHistoryR0Result:
        """Entrega el ancla privada una sola vez y la descarta siempre."""

        if (
            self._state is not BitrixHistoryR0HandoffState.ARMED
            or self._anchor is None
            or self._reader_started
        ):
            raise RuntimeError("bitrix_history_handoff_not_armed")
        self._reader_started = True
        anchor = self._anchor
        try:
            result = await reader(anchor)
            if not isinstance(result, BitrixHistoryR0Result):
                raise RuntimeError("bitrix_history_reader_result_invalid")
            return result
        except asyncio.CancelledError:
            self._state = BitrixHistoryR0HandoffState.CLOSED
            self._reason = "bitrix_history_handoff_cancelled"
            raise
        finally:
            self._discard_anchor()

    async def __aenter__(self) -> "BitrixHistoryR0InMemoryHandoff":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()


async def prepare_stored_oauth_history_handoff_once(
    *,
    settings: ConnectorSettings,
    timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    execute_preflight: PreflightExecutor = (
        execute_stored_oauth_history_preflight_once
    ),
) -> BitrixHistoryR0InMemoryHandoff:
    """Prepara el handoff sin autorizar ni ejecutar el lector de historial."""

    try:
        outcome = await execute_preflight(
            settings=settings,
            timeout_seconds=timeout_seconds,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        return BitrixHistoryR0InMemoryHandoff(
            state=BitrixHistoryR0HandoffState.NO_GO,
            reason="bitrix_history_handoff_preflight_failed_safe",
            resources_closed=False,
        )
    if not isinstance(outcome, BitrixHistoryR0PreflightOutcome):
        return BitrixHistoryR0InMemoryHandoff(
            state=BitrixHistoryR0HandoffState.NO_GO,
            reason="bitrix_history_handoff_preflight_invalid",
            resources_closed=False,
        )
    return BitrixHistoryR0InMemoryHandoff.from_preflight(outcome)


__all__ = [
    "MAX_AUTHORIZATION_WAIT_SECONDS",
    "ArmedReader",
    "AuthorizationGate",
    "BitrixHistoryR0HandoffDecision",
    "BitrixHistoryR0HandoffSnapshot",
    "BitrixHistoryR0HandoffState",
    "BitrixHistoryR0InMemoryHandoff",
    "PreflightExecutor",
    "prepare_stored_oauth_history_handoff_once",
]
