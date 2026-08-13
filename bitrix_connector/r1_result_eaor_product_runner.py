"""Two-phase one-shot runner for an already accepted product R1 EAOR.

Construction receives only deferred factories.  Product owners are built by the
existing product port when their stage begins; this module performs no I/O by
itself and never sends the human message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .r1_result_eaor_coordinator import (
    R1ResultEaorCoordinator,
    R1ResultEaorSnapshot,
)
from .r1_result_eaor_product_port import build_dormant_product_eaor_coordinator


@dataclass(frozen=True)
class R1ProductExecutionFactories:
    provisioning_factory: Callable
    activation_factory: Callable
    session_factory: Callable

    def __post_init__(self) -> None:
        if not all(callable(item) for item in (
            self.provisioning_factory,
            self.activation_factory,
            self.session_factory,
        )):
            raise TypeError("r1_product_execution_factory_invalid")


class R1ResultEaorProductRunner:
    """Owns the exact pre-human run and one resume-or-close decision."""

    __slots__ = ("_acceptance", "_coordinator", "_started", "_terminal")

    def __init__(
        self,
        *,
        coordinator: R1ResultEaorCoordinator,
        acceptance: str,
    ) -> None:
        if type(coordinator) is not R1ResultEaorCoordinator:
            raise TypeError("r1_product_runner_coordinator_invalid")
        self._coordinator = coordinator
        self._acceptance = acceptance
        self._started = False
        self._terminal = False

    async def run_until_human_once(self) -> R1ResultEaorSnapshot:
        if self._started or self._terminal:
            raise RuntimeError("r1_product_runner_reused")
        self._started = True
        result = await self._coordinator.run_until_human_once(
            acceptance=self._acceptance
        )
        if result.state != "ATTENTION-REQUIRED":
            self._terminal = True
        return result

    async def resume_after_human_once(self) -> R1ResultEaorSnapshot:
        if not self._started or self._terminal:
            raise RuntimeError("r1_product_runner_not_waiting")
        self._terminal = True
        return await self._coordinator.resume_after_human_once()

    async def close_waiting_once(self) -> R1ResultEaorSnapshot:
        if not self._started or self._terminal:
            raise RuntimeError("r1_product_runner_not_waiting")
        self._terminal = True
        return await self._coordinator.close_waiting_once()

    def __repr__(self) -> str:
        return "R1ResultEaorProductRunner(<redacted>)"


def build_dormant_product_runner(
    *,
    factories: R1ProductExecutionFactories,
    acceptance: str,
    coordinator_builder=build_dormant_product_eaor_coordinator,
) -> R1ResultEaorProductRunner:
    """Build the coordinator without invoking any supplied product factory."""

    if type(factories) is not R1ProductExecutionFactories:
        raise TypeError("r1_product_execution_factories_invalid")
    coordinator = coordinator_builder(
        provisioning_factory=factories.provisioning_factory,
        activation_factory=factories.activation_factory,
        session_factory=factories.session_factory,
    )
    return R1ResultEaorProductRunner(
        coordinator=coordinator,
        acceptance=acceptance,
    )


__all__ = [
    "R1ProductExecutionFactories",
    "R1ResultEaorProductRunner",
    "build_dormant_product_runner",
]
