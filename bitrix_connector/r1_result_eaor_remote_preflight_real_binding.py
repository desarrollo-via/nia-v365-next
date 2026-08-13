"""Dormant link from the daily EAOR to the exact real Azure diagnostic adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from .r1_azure_diagnostic_real_attempt import (
    build_real_r1_azure_diagnostic_coordinator,
)
from .r1_key_vault_linux_provisioning_real_binding import (
    ExactAzureCliCommandRunner,
    ExactDormantHealthReader,
)
from .r1_result_eaor_remote_preflight_coordinator import (
    R1RemotePreflightEaorCoordinator,
)


CONSTRUCTION_AUDIT_CONFIRMATION = (
    "AUDITAR CONSTRUCCION EAOR R1 REMOTA SOLO LOCAL SIN EJECUTAR"
)


@dataclass(frozen=True)
class R1RemotePreflightRealBindingPreview:
    state: Literal["DORMANT", "BOUND-DORMANT"] = "DORMANT"
    coordinator_constructions: int = 0
    diagnostic_constructions: Literal[0] = 0
    runner_constructions: Literal[0] = 0
    health_reader_constructions: Literal[0] = 0
    local_state_guard_calls: Literal[0] = 0
    run_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    protected_source_opens: Literal[0] = 0
    secret_reads: Literal[0] = 0
    mutations: Literal[0] = 0
    bitrix_calls: Literal[0] = 0
    messages_sent: Literal[0] = 0
    execution_authorized: Literal[False] = False


class R1RemotePreflightDormantRealBinding:
    """Stores exact builders; none are invoked while the coordinator is built."""

    __slots__ = (
        "_built", "_diagnostic_builder", "_health_factory",
        "_local_state_guard", "_runner_factory",
    )

    def __init__(
        self,
        *,
        local_state_guard: Callable[[], bool],
        diagnostic_builder=build_real_r1_azure_diagnostic_coordinator,
        runner_factory=ExactAzureCliCommandRunner,
        health_factory=ExactDormantHealthReader,
    ) -> None:
        if not all(callable(item) for item in (
            local_state_guard, diagnostic_builder, runner_factory, health_factory
        )):
            raise TypeError("r1_remote_preflight_real_binding_dependency_invalid")
        self._local_state_guard = local_state_guard
        self._diagnostic_builder = diagnostic_builder
        self._runner_factory = runner_factory
        self._health_factory = health_factory
        self._built = False

    def preview(self) -> R1RemotePreflightRealBindingPreview:
        return R1RemotePreflightRealBindingPreview(
            state="BOUND-DORMANT" if self._built else "DORMANT",
            coordinator_constructions=1 if self._built else 0,
        )

    def build_coordinator_once(self) -> R1RemotePreflightEaorCoordinator:
        if self._built:
            raise RuntimeError("r1_remote_preflight_real_binding_reused")
        self._built = True
        diagnostic_builder = self._diagnostic_builder
        local_state_guard = self._local_state_guard
        runner_factory = self._runner_factory
        health_factory = self._health_factory

        def diagnostic_factory():
            return diagnostic_builder(
                local_state_guard=local_state_guard,
                max_attempts=3,
                runner_factory=runner_factory,
                health_factory=health_factory,
            )

        return R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory
        )

    def __repr__(self) -> str:
        return "R1RemotePreflightDormantRealBinding(<redacted>)"


def build_dormant_real_remote_preflight_binding(
    *, local_state_guard: Callable[[], bool]
) -> R1RemotePreflightDormantRealBinding:
    return R1RemotePreflightDormantRealBinding(
        local_state_guard=local_state_guard
    )


__all__ = [
    "CONSTRUCTION_AUDIT_CONFIRMATION",
    "R1RemotePreflightDormantRealBinding",
    "R1RemotePreflightRealBindingPreview",
    "build_dormant_real_remote_preflight_binding",
]
