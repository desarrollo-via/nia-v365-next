"""Hermetic coordinator for the result-oriented R1 autonomous envelope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


EAOR_ID = "NIA-NEXT-R1-EAOR-2026-08-13-V1"
EAOR_ACCEPTANCE = "sp"

StageState = Literal[
    "PROVISIONED-DORMANT-VERIFIED",
    "ACTIVATED-VERIFIED",
    "ATTENTION-REQUIRED",
    "VERIFIED-RESTORED",
    "FAILED-RESTORED",
    "EXPIRED-RESTORED",
    "NO-GO-REMAINDER",
]
EaorState = Literal[
    "INERT",
    "NO-GO-ACCEPTANCE",
    "FAILED-RESTORED",
    "NO-GO-REMAINDER",
    "ATTENTION-REQUIRED",
    "VERIFIED-RESTORED",
]


@dataclass(frozen=True)
class R1EaorStageResult:
    state: StageState
    resources_closed: bool = True
    local_state_preserved: bool = True


class R1EaorPort(Protocol):
    async def provision_once(self) -> R1EaorStageResult: ...
    async def activate_once(self) -> R1EaorStageResult: ...
    async def arm_session_once(self) -> R1EaorStageResult: ...
    async def observe_after_human_once(self) -> R1EaorStageResult: ...
    async def restore_activation_once(self) -> R1EaorStageResult: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class R1ResultEaorSnapshot:
    state: EaorState = "INERT"
    eaor_id: Literal["NIA-NEXT-R1-EAOR-2026-08-13-V1"] = EAOR_ID
    acceptance_calls: int = 0
    provisioning_calls: int = 0
    activation_calls: int = 0
    session_arm_calls: int = 0
    observation_calls: int = 0
    activation_restore_calls: int = 0
    human_message_calls: Literal[0] = 0
    resources_closed: bool = False
    human_message_required_now: bool = False
    pre_event_lease_state: str = "INERT"
    external_retries: Literal[0] = 0


class R1ResultEaorCoordinator:
    """Runs all pre-human stages and resumes once after the manual message."""

    __slots__ = ("_counts", "_port", "_state", "_waiting", "_used")

    def __init__(self, *, port: R1EaorPort) -> None:
        required = (
            "provision_once", "activate_once", "arm_session_once",
            "observe_after_human_once", "restore_activation_once", "close",
        )
        if any(not callable(getattr(port, name, None)) for name in required):
            raise TypeError("r1_eaor_port_invalid")
        self._port: R1EaorPort | None = port
        self._state: EaorState = "INERT"
        self._used = False
        self._waiting = False
        self._counts = {
            "acceptance": 0,
            "provisioning": 0,
            "activation": 0,
            "arm": 0,
            "observation": 0,
            "restore_activation": 0,
        }

    def _snapshot(
        self, *, closed: bool = False, attention: bool = False
    ) -> R1ResultEaorSnapshot:
        return R1ResultEaorSnapshot(
            state=self._state,
            acceptance_calls=self._counts["acceptance"],
            provisioning_calls=self._counts["provisioning"],
            activation_calls=self._counts["activation"],
            session_arm_calls=self._counts["arm"],
            observation_calls=self._counts["observation"],
            activation_restore_calls=self._counts["restore_activation"],
            resources_closed=closed,
            human_message_required_now=attention,
            pre_event_lease_state="AWAITING-EVENT" if attention else "INERT",
        )

    async def _close_once(self) -> bool:
        port, self._port = self._port, None
        if port is None:
            return True
        try:
            await port.close()
        except BaseException:
            return False
        return True

    async def _restore_activation(self) -> bool:
        port = self._port
        if port is None:
            return False
        self._counts["restore_activation"] = 1
        try:
            result = await port.restore_activation_once()
        except BaseException:
            return False
        return (
            type(result) is R1EaorStageResult
            and result.state == "VERIFIED-RESTORED"
            and result.resources_closed
        )

    async def run_until_human_once(
        self, *, acceptance: str
    ) -> R1ResultEaorSnapshot:
        if self._used:
            raise RuntimeError("r1_eaor_reused")
        self._used = True
        self._counts["acceptance"] = 1
        if acceptance != EAOR_ACCEPTANCE:
            self._state = "NO-GO-ACCEPTANCE"
            return self._snapshot(closed=await self._close_once())
        port = self._port
        if port is None:
            raise RuntimeError("r1_eaor_port_unavailable")
        stages = (
            ("provisioning", port.provision_once, "PROVISIONED-DORMANT-VERIFIED"),
            ("activation", port.activate_once, "ACTIVATED-VERIFIED"),
            ("arm", port.arm_session_once, "ATTENTION-REQUIRED"),
        )
        for name, operation, expected in stages:
            self._counts[name] = 1
            try:
                result = await operation()
            except BaseException:
                result = R1EaorStageResult("NO-GO-REMAINDER", False, False)
            if type(result) is not R1EaorStageResult or not result.resources_closed:
                self._state = "NO-GO-REMAINDER"
                return self._snapshot(closed=await self._close_once())
            if result.state != expected:
                if name != "provisioning":
                    restored = await self._restore_activation()
                    self._state = "FAILED-RESTORED" if restored else "NO-GO-REMAINDER"
                else:
                    self._state = (
                        "FAILED-RESTORED"
                        if result.state == "FAILED-RESTORED"
                        else "NO-GO-REMAINDER"
                    )
                return self._snapshot(closed=await self._close_once())
        self._waiting = True
        self._state = "ATTENTION-REQUIRED"
        return self._snapshot(attention=True)

    async def resume_after_human_once(self) -> R1ResultEaorSnapshot:
        if not self._waiting or self._state != "ATTENTION-REQUIRED":
            raise RuntimeError("r1_eaor_not_waiting_for_human")
        self._waiting = False
        port = self._port
        if port is None:
            raise RuntimeError("r1_eaor_port_unavailable")
        self._counts["observation"] = 1
        try:
            observed = await port.observe_after_human_once()
        except BaseException:
            observed = R1EaorStageResult("NO-GO-REMAINDER", False, False)
        activation_restored = await self._restore_activation()
        closed = await self._close_once()
        if (
            type(observed) is R1EaorStageResult
            and observed.state == "VERIFIED-RESTORED"
            and observed.resources_closed
            and activation_restored
            and closed
        ):
            self._state = "VERIFIED-RESTORED"
        elif (
            type(observed) is R1EaorStageResult
            and observed.state in {"FAILED-RESTORED", "EXPIRED-RESTORED"}
            and observed.resources_closed
            and activation_restored
            and closed
        ):
            self._state = "FAILED-RESTORED"
        else:
            self._state = "NO-GO-REMAINDER"
        return self._snapshot(closed=closed)

    async def close_waiting_once(self) -> R1ResultEaorSnapshot:
        """Abort an armed session, restoring participant before activation."""

        if not self._waiting or self._state != "ATTENTION-REQUIRED":
            raise RuntimeError("r1_eaor_not_waiting_for_human")
        self._waiting = False
        port = self._port
        abort = getattr(port, "abort_waiting_once", None)
        restored = False
        if callable(abort):
            try:
                result = await abort()
                restored = bool(
                    type(result) is R1EaorStageResult
                    and result.state == "VERIFIED-RESTORED"
                    and result.resources_closed
                )
            except BaseException:
                restored = False
        closed = await self._close_once()
        self._state = (
            "FAILED-RESTORED" if restored and closed else "NO-GO-REMAINDER"
        )
        return self._snapshot(closed=closed)


__all__ = [
    "EAOR_ACCEPTANCE", "EAOR_ID", "R1EaorPort", "R1EaorStageResult",
    "R1ResultEaorCoordinator", "R1ResultEaorSnapshot",
]
