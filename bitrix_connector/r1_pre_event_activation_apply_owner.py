"""Hermetic transactional owner for the exact three-switch R1 activation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .r1_pre_event_activation_preflight import (
    R0_SETTING,
    R1_SETTING,
    STRATEGY_SETTING,
    R1ActivationPreflight,
)


FIRST_ACTIVATION_CONFIRMATION = (
    "PRIMERA CONFIRMACION R1 ACTIVACION APPSETTINGS-3"
)
SECOND_ACTIVATION_CONFIRMATION = (
    "SEGUNDA CONFIRMACION R1 ACTIVACION APPSETTINGS-3 EJECUCION INMEDIATA"
)
ACTIVATION_VALUES = (
    (R0_SETTING, "false"),
    (R1_SETTING, "true"),
    (STRATEGY_SETTING, "pre-event"),
)

ActivationState = Literal[
    "AWAITING-SECOND-CONFIRMATION",
    "ACTIVATED-VERIFIED",
    "VERIFIED-RESTORED",
    "FAILED-RESTORED",
    "NO-GO-FIRST-CONFIRMATION",
    "NO-GO-PREFLIGHT",
    "NO-GO-SECOND-CONFIRMATION",
    "NO-GO-REMAINDER",
]


class R1ActivationApplyControl(Protocol):
    async def apply_exact_switches_once(
        self, values: tuple[tuple[str, str], ...]
    ) -> None: ...

    async def restart_after_apply_once(self) -> None: ...

    async def verify_active_once(self) -> bool: ...

    async def restore_exact_switches_once(
        self, rollback_plan: tuple[str, ...]
    ) -> None: ...

    async def restart_after_restore_once(self) -> None: ...

    async def verify_dormant_once(self) -> bool: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class R1ActivationApplySnapshot:
    state: ActivationState
    first_confirmation_calls: int = 0
    second_confirmation_calls: int = 0
    switch_apply_calls: int = 0
    restart_after_apply_calls: int = 0
    active_verification_calls: int = 0
    rollback_calls: int = 0
    restart_after_rollback_calls: int = 0
    dormant_verification_calls: int = 0
    resources_closed: bool = False
    protected_source_opens: Literal[0] = 0
    secret_reads: Literal[0] = 0
    participant_mutations: Literal[0] = 0


class R1PreEventActivationApplyOwner:
    """Keeps apply and exact rollback in one finite, injected lifecycle."""

    __slots__ = (
        "_control",
        "_counts",
        "_prepared",
        "_rollback_plan",
        "_state",
        "_used",
    )

    def __init__(self, *, control: R1ActivationApplyControl) -> None:
        required = (
            "apply_exact_switches_once",
            "restart_after_apply_once",
            "verify_active_once",
            "restore_exact_switches_once",
            "restart_after_restore_once",
            "verify_dormant_once",
            "close",
        )
        if any(not callable(getattr(control, name, None)) for name in required):
            raise TypeError("r1_activation_apply_control_invalid")
        self._control: R1ActivationApplyControl | None = control
        self._prepared = False
        self._used = False
        self._rollback_plan: tuple[str, ...] = ()
        self._state: ActivationState = "NO-GO-PREFLIGHT"
        self._counts = {
            "first": 0,
            "second": 0,
            "apply": 0,
            "restart_apply": 0,
            "verify_active": 0,
            "rollback": 0,
            "restart_rollback": 0,
            "verify_dormant": 0,
        }

    def _snapshot(self, *, resources_closed: bool = False) -> R1ActivationApplySnapshot:
        return R1ActivationApplySnapshot(
            state=self._state,
            first_confirmation_calls=self._counts["first"],
            second_confirmation_calls=self._counts["second"],
            switch_apply_calls=self._counts["apply"],
            restart_after_apply_calls=self._counts["restart_apply"],
            active_verification_calls=self._counts["verify_active"],
            rollback_calls=self._counts["rollback"],
            restart_after_rollback_calls=self._counts["restart_rollback"],
            dormant_verification_calls=self._counts["verify_dormant"],
            resources_closed=resources_closed,
        )

    async def _close_once(self) -> bool:
        control, self._control = self._control, None
        if control is None:
            return True
        try:
            await control.close()
        except BaseException:
            return False
        return True

    async def prepare_once(
        self,
        *,
        preflight: R1ActivationPreflight,
        first_confirmation: str,
    ) -> R1ActivationApplySnapshot:
        if self._used:
            raise RuntimeError("r1_activation_apply_owner_reused")
        self._used = True
        self._counts["first"] = 1
        if first_confirmation != FIRST_ACTIVATION_CONFIRMATION:
            self._state = "NO-GO-FIRST-CONFIRMATION"
            return self._snapshot(resources_closed=await self._close_once())
        if (
            type(preflight) is not R1ActivationPreflight
            or preflight.state != "READY-FIRST-CONFIRMATION"
            or not preflight.switch_baseline_verified
            or not preflight.participant_baseline_verified
            or len(preflight.rollback_plan) != 3
        ):
            self._state = "NO-GO-PREFLIGHT"
            return self._snapshot(resources_closed=await self._close_once())
        self._rollback_plan = preflight.rollback_plan
        self._prepared = True
        self._state = "AWAITING-SECOND-CONFIRMATION"
        return self._snapshot()

    async def _restore(self, *, failure_state: ActivationState) -> R1ActivationApplySnapshot:
        control = self._control
        restored = control is not None
        if control is not None:
            try:
                self._counts["rollback"] = 1
                await control.restore_exact_switches_once(self._rollback_plan)
                self._counts["restart_rollback"] = 1
                await control.restart_after_restore_once()
                self._counts["verify_dormant"] = 1
                restored = await control.verify_dormant_once() is True
            except BaseException:
                restored = False
        closed = await self._close_once()
        self._state = failure_state if restored and closed else "NO-GO-REMAINDER"
        return self._snapshot(resources_closed=closed)

    async def execute_once(
        self, *, second_confirmation: str
    ) -> R1ActivationApplySnapshot:
        if not self._prepared:
            raise RuntimeError("r1_activation_apply_owner_not_prepared")
        self._prepared = False
        self._counts["second"] = 1
        if second_confirmation != SECOND_ACTIVATION_CONFIRMATION:
            self._state = "NO-GO-SECOND-CONFIRMATION"
            return self._snapshot(resources_closed=await self._close_once())
        control = self._control
        if control is None:
            raise RuntimeError("r1_activation_apply_control_unavailable")
        try:
            self._counts["apply"] = 1
            await control.apply_exact_switches_once(ACTIVATION_VALUES)
            self._counts["restart_apply"] = 1
            await control.restart_after_apply_once()
            self._counts["verify_active"] = 1
            if await control.verify_active_once() is not True:
                raise RuntimeError("r1_activation_active_postread_failed")
        except BaseException:
            return await self._restore(failure_state="FAILED-RESTORED")
        self._state = "ACTIVATED-VERIFIED"
        return self._snapshot()

    async def restore_once(self) -> R1ActivationApplySnapshot:
        if self._state != "ACTIVATED-VERIFIED":
            raise RuntimeError("r1_activation_apply_owner_not_active")
        return await self._restore(failure_state="VERIFIED-RESTORED")


__all__ = [
    "ACTIVATION_VALUES",
    "FIRST_ACTIVATION_CONFIRMATION",
    "R1ActivationApplySnapshot",
    "R1PreEventActivationApplyOwner",
    "SECOND_ACTIVATION_CONFIRMATION",
]
