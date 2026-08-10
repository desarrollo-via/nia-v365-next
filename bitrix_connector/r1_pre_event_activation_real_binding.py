"""Dormant real-ready boundary for the R1 activation evidence collector."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .r1_pre_event_activation_evidence_collector import (
    R1ActivationEvidenceCollector,
    SanitizedDeploymentEvidence,
    SanitizedParticipantEvidence,
    SanitizedProtectedSourceEvidence,
)
from .r1_pre_event_activation_preflight import SanitizedSwitchBaseline


DeploymentOperation = Callable[..., Awaitable[SanitizedDeploymentEvidence]]
ProtectedOperation = Callable[..., Awaitable[SanitizedProtectedSourceEvidence]]
SwitchOperation = Callable[
    ..., Awaitable[tuple[SanitizedSwitchBaseline, ...]]
]
ParticipantOperation = Callable[..., Awaitable[SanitizedParticipantEvidence]]


@dataclass(frozen=True)
class R1ActivationRealOperations:
    deployment: DeploymentOperation
    protected_source: ProtectedOperation
    switches: SwitchOperation
    participants: ParticipantOperation

    def __post_init__(self) -> None:
        if not all(
            callable(item)
            for item in (
                self.deployment,
                self.protected_source,
                self.switches,
                self.participants,
            )
        ):
            raise TypeError("r1_activation_real_operation_invalid")


class _DeferredOneShotProbe:
    __slots__ = ("_operation", "_used")

    def __init__(self, operation: Callable[..., Awaitable[object]]) -> None:
        if not callable(operation):
            raise TypeError("r1_activation_real_operation_invalid")
        self._operation = operation
        self._used = False

    async def collect(self, **scope):
        operation, self._operation = self._operation, None
        if self._used or operation is None:
            self._used = True
            raise RuntimeError("r1_activation_real_probe_reused")
        self._used = True
        return await operation(**scope)

    def __repr__(self) -> str:
        return "_DeferredOneShotProbe(<redacted>)"


class _R1ActivationRealBindingPermit:
    """Capability reserved for the future exact authorization gate."""

    __slots__ = ()


@dataclass(frozen=True)
class R1ActivationRealBindingPreview:
    state: Literal["WAITING-EXACT-AUTHORIZATION"] = (
        "WAITING-EXACT-AUTHORIZATION"
    )
    gate_permit_required: Literal[True] = True
    direct_build_allowed: Literal[False] = False
    operations_bound: Literal[True] = True
    permit_consumed: bool = False
    collector_constructions: int = 0
    operation_calls: Literal[0] = 0
    protected_source_open_calls: Literal[0] = 0
    credential_reads: Literal[0] = 0
    oauth_reads: Literal[0] = 0
    app_setting_reads: Literal[0] = 0
    participant_reads: Literal[0] = 0
    external_calls: Literal[0] = 0
    mutations: Literal[0] = 0
    activation_authorized: Literal[False] = False


class R1ActivationDormantRealBinding:
    """Binds deferred operations without executing or inspecting them."""

    __slots__ = (
        "_operations",
        "_permit_consumed",
        "_used",
        "collector_constructions",
    )

    def __init__(self, *, operations: R1ActivationRealOperations) -> None:
        if type(operations) is not R1ActivationRealOperations:
            raise TypeError("r1_activation_real_operations_invalid")
        self._operations: R1ActivationRealOperations | None = operations
        self._used = False
        self._permit_consumed = False
        self.collector_constructions = 0

    def __call__(self) -> R1ActivationEvidenceCollector:
        raise RuntimeError("r1_activation_real_binding_permit_required")

    def build_after_gate_once(
        self, permit: _R1ActivationRealBindingPermit
    ) -> R1ActivationEvidenceCollector:
        operations, self._operations = self._operations, None
        if (
            self._used
            or type(permit) is not _R1ActivationRealBindingPermit
            or operations is None
        ):
            self._used = True
            raise RuntimeError("r1_activation_real_binding_reuse_or_permit_invalid")
        self._used = True
        self._permit_consumed = True
        collector = R1ActivationEvidenceCollector(
            deployment_probe=_DeferredOneShotProbe(operations.deployment),
            protected_probe=_DeferredOneShotProbe(operations.protected_source),
            switch_probe=_DeferredOneShotProbe(operations.switches),
            participant_probe=_DeferredOneShotProbe(operations.participants),
        )
        self.collector_constructions = 1
        return collector

    def preview(self) -> R1ActivationRealBindingPreview:
        return R1ActivationRealBindingPreview(
            permit_consumed=self._permit_consumed,
            collector_constructions=self.collector_constructions,
        )

    def __repr__(self) -> str:
        return "R1ActivationDormantRealBinding(<redacted>)"


__all__ = [
    "R1ActivationDormantRealBinding",
    "R1ActivationRealBindingPreview",
    "R1ActivationRealOperations",
]
