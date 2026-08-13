"""Exact, inert adapter from the R1 activation owner to the EAOR stage port."""

from __future__ import annotations

import inspect
from typing import Callable

from .r1_pre_event_activation_apply_owner import (
    FIRST_ACTIVATION_CONFIRMATION,
    SECOND_ACTIVATION_CONFIRMATION,
    R1PreEventActivationApplyOwner,
)
from .r1_pre_event_activation_preflight import R1ActivationPreflight
from .r1_result_eaor_coordinator import R1EaorStageResult


class R1EaorActivationOwnerAdapter:
    """Supplies frozen owner literals only inside an already accepted EAOR."""

    __slots__ = ("_active", "_owner", "_preflight_supplier", "_restored", "_used")

    def __init__(
        self,
        *,
        owner: R1PreEventActivationApplyOwner,
        preflight_supplier: Callable[[], R1ActivationPreflight],
    ) -> None:
        if (
            type(owner) is not R1PreEventActivationApplyOwner
            or not callable(preflight_supplier)
        ):
            raise TypeError("r1_eaor_activation_adapter_dependency_invalid")
        self._owner = owner
        self._preflight_supplier = preflight_supplier
        self._used = False
        self._active = False
        self._restored = False

    async def activate_once(self) -> R1EaorStageResult:
        if self._used:
            raise RuntimeError("r1_eaor_activation_adapter_reused")
        self._used = True
        supplied = self._preflight_supplier()
        preflight = await supplied if inspect.isawaitable(supplied) else supplied
        prepared = await self._owner.prepare_once(
            preflight=preflight,
            first_confirmation=FIRST_ACTIVATION_CONFIRMATION,
        )
        if prepared.state != "AWAITING-SECOND-CONFIRMATION":
            return R1EaorStageResult(
                "NO-GO-REMAINDER",
                resources_closed=prepared.resources_closed,
            )
        result = await self._owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )
        if result.state == "ACTIVATED-VERIFIED":
            self._active = True
            # The exact binding closes each command runner and HTTP client;
            # only the immutable rollback state remains in the owner.
            return R1EaorStageResult("ACTIVATED-VERIFIED")
        if result.state == "FAILED-RESTORED" and result.resources_closed:
            self._restored = True
        state = (
            "FAILED-RESTORED"
            if result.state == "FAILED-RESTORED"
            else "NO-GO-REMAINDER"
        )
        return R1EaorStageResult(
            state,
            resources_closed=result.resources_closed,
        )

    async def restore_once(self) -> R1EaorStageResult:
        if self._restored and not self._active:
            return R1EaorStageResult("VERIFIED-RESTORED")
        if not self._active or self._restored:
            raise RuntimeError("r1_eaor_activation_adapter_not_active")
        self._restored = True
        result = await self._owner.restore_once()
        self._active = False
        state = (
            "VERIFIED-RESTORED"
            if result.state == "VERIFIED-RESTORED"
            else "NO-GO-REMAINDER"
        )
        return R1EaorStageResult(
            state,
            resources_closed=result.resources_closed,
        )

    def __repr__(self) -> str:
        return "R1EaorActivationOwnerAdapter(<redacted>)"


__all__ = ["R1EaorActivationOwnerAdapter"]
