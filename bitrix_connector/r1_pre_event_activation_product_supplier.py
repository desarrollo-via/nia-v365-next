"""Dormant one-shot supplier for the asynchronous product R1 preflight."""

from __future__ import annotations

from .r1_pre_event_activation_operation_contract import (
    PREFLIGHT_AUTHORIZATION_LITERAL,
    R1ActivationPreflightAuthorizationGate,
    R1ActivationRealOperationReadiness,
)
from .r1_pre_event_activation_preflight import R1ActivationPreflight
from .r1_pre_event_activation_real_binding import (
    R1ActivationDormantRealBinding,
    R1ActivationRealOperations,
)


class R1ActivationProductPreflightSupplier:
    """Consumes the internal technical gate and returns sanitized preflight."""

    __slots__ = ("_gate", "_used")

    def __init__(
        self, *, operations: R1ActivationRealOperations,
        readiness: R1ActivationRealOperationReadiness,
    ) -> None:
        if (
            type(operations) is not R1ActivationRealOperations
            or type(readiness) is not R1ActivationRealOperationReadiness
        ):
            raise TypeError("r1_activation_product_supplier_dependency_invalid")
        self._gate = R1ActivationPreflightAuthorizationGate(
            binding=R1ActivationDormantRealBinding(operations=operations),
            readiness=readiness,
        )
        self._used = False

    async def __call__(self) -> R1ActivationPreflight:
        if self._used:
            raise RuntimeError("r1_activation_product_supplier_reused")
        self._used = True
        outcome = self._gate.authorize_once(PREFLIGHT_AUTHORIZATION_LITERAL)
        if outcome.state != "COLLECTOR-MATERIALIZED" or outcome.collector is None:
            return R1ActivationPreflight()
        collection = await outcome.collector.collect()
        if collection.state != "EVIDENCE-COLLECTED":
            return R1ActivationPreflight()
        return collection.preflight

    def __repr__(self) -> str:
        return "R1ActivationProductPreflightSupplier(<redacted>)"


__all__ = ["R1ActivationProductPreflightSupplier"]
