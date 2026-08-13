"""External-supervisor adapter for the R1 session mounted in the Web App."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Protocol

from .bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from .bitrix_event_scoped_r1_gate import (
    EVENT_R1_FIRST_CONFIRMATION,
    EVENT_R1_SECOND_CONFIRMATION,
)
from .r1_result_eaor_coordinator import R1EaorStageResult


class R1RemoteSessionControlClient(Protocol):
    async def first_confirmation_once(
        self, confirmation: str
    ) -> EventR1ControlSnapshot: ...

    async def second_confirmation_once(
        self, confirmation: str
    ) -> EventR1ControlSnapshot: ...

    async def status_once(self) -> EventR1ControlSnapshot: ...

    async def disarm_once(self) -> EventR1ControlSnapshot: ...

    async def close(self) -> None: ...


class R1EaorRemoteSessionAdapter:
    """Controls the already-mounted host owner without sending a message."""

    __slots__ = (
        "_armed", "_client", "_clock", "_closed", "_observed",
        "_poll_interval", "_sleeper", "_timeout",
    )

    def __init__(
        self,
        *,
        client: R1RemoteSessionControlClient,
        poll_interval_seconds: int = 15,
        observation_timeout_seconds: int = 600,
        clock: Callable[[], float] = time.monotonic,
        sleeper=asyncio.sleep,
    ) -> None:
        required = (
            "first_confirmation_once", "second_confirmation_once",
            "status_once", "disarm_once", "close",
        )
        if (
            any(not callable(getattr(client, name, None)) for name in required)
            or type(poll_interval_seconds) is not int
            or not 15 <= poll_interval_seconds <= 30
            or type(observation_timeout_seconds) is not int
            or not 60 <= observation_timeout_seconds <= 600
            or not callable(clock)
            or not callable(sleeper)
        ):
            raise TypeError("r1_remote_session_adapter_dependency_invalid")
        self._client = client
        self._poll_interval = poll_interval_seconds
        self._timeout = observation_timeout_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._armed = False
        self._observed = False
        self._closed = False

    async def arm_once(self) -> R1EaorStageResult:
        if self._armed or self._closed:
            raise RuntimeError("r1_remote_session_adapter_reused")
        first = await self._client.first_confirmation_once(
            EVENT_R1_FIRST_CONFIRMATION
        )
        if (
            type(first) is not EventR1ControlSnapshot
            or first.state != "AWAITING-SECOND-CONFIRMATION"
        ):
            await self.close()
            return R1EaorStageResult("NO-GO-REMAINDER")
        self._armed = True
        second = await self._client.second_confirmation_once(
            EVENT_R1_SECOND_CONFIRMATION
        )
        exact = bool(
            type(second) is EventR1ControlSnapshot
            and second.state == "ATTENTION-REQUIRED"
            and second.attention_required_now
            and second.human_message_required_now
            and second.pre_event_lease_bound
            and second.pre_event_lease_state == "AWAITING-EVENT"
            and second.participant_arm_attempts == 1
            and second.human_message_authorizations == 1
        )
        if not exact:
            await self.close()
            return R1EaorStageResult("NO-GO-REMAINDER")
        return R1EaorStageResult("ATTENTION-REQUIRED")

    async def observe_after_human_once(self) -> R1EaorStageResult:
        if not self._armed or self._observed or self._closed:
            raise RuntimeError("r1_remote_session_adapter_not_armed")
        self._observed = True
        deadline = self._clock() + self._timeout
        while True:
            snapshot = await self._client.status_once()
            if type(snapshot) is not EventR1ControlSnapshot:
                await self.close()
                return R1EaorStageResult("NO-GO-REMAINDER", False)
            restored = bool(
                snapshot.pre_event_lease_state in {"RESTORED", "EXPIRED-RESTORED"}
                and snapshot.participant_rollback_attempts == 1
                and snapshot.participant_rollback_verified
            )
            if snapshot.state == "VERIFIED" and restored:
                self._armed = False
                await self._close_client_once()
                return R1EaorStageResult("VERIFIED-RESTORED")
            if snapshot.state == "EXPIRED" and restored:
                self._armed = False
                await self._close_client_once()
                return R1EaorStageResult("EXPIRED-RESTORED")
            if snapshot.state in {"NO-GO", "ROLLED-BACK", "DISARMED"}:
                if not restored:
                    try:
                        restored = await self._disarm_once()
                    except BaseException:
                        restored = False
                self._armed = not restored
                await self._close_client_once()
                return R1EaorStageResult(
                    "FAILED-RESTORED" if restored else "NO-GO-REMAINDER",
                    resources_closed=restored,
                )
            if self._clock() >= deadline:
                restored = await self._disarm_once()
                await self._close_client_once()
                return R1EaorStageResult(
                    "EXPIRED-RESTORED" if restored else "NO-GO-REMAINDER",
                    resources_closed=restored,
                )
            await self._sleeper(self._poll_interval)

    async def _close_client_once(self) -> None:
        if self._closed:
            return
        self._closed = True
        client, self._client = self._client, None
        if client is not None:
            await client.close()

    async def close(self) -> None:
        if self._closed:
            return
        client = self._client
        restored = await self._disarm_once() if self._armed else True
        await self._close_client_once()
        if not restored:
            raise RuntimeError("r1_remote_session_close_remainder")

    async def _disarm_once(self) -> bool:
        client = self._client
        if client is None:
            return False
        result = await client.disarm_once()
        restored = bool(
            type(result) is EventR1ControlSnapshot
            and result.state == "DISARMED"
            and result.participant_rollback_attempts == 1
            and result.participant_rollback_verified
        )
        self._armed = not restored
        return restored

    def __repr__(self) -> str:
        return "R1EaorRemoteSessionAdapter(<redacted>)"


__all__ = ["R1EaorRemoteSessionAdapter", "R1RemoteSessionControlClient"]
