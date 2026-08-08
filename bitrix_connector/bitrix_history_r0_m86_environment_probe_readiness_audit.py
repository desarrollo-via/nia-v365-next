"""Auditoría M86-AG puramente declarativa previa a mostrar el literal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantBindingContract,
)
from .bitrix_history_r0_m86_environment_probe_authorization import (
    M86AFAuthorizationContract,
)


@dataclass(frozen=True)
class M86AGReadinessSnapshot:
    phase: Literal["M86-AG"] = "M86-AG"
    state: Literal["READY-TO-SHOW-AUTHORIZATION", "NO-GO"] = "NO-GO"
    failure_category: Literal["none", "binding_contract_invalid", "literal_contract_invalid"] = (
        "binding_contract_invalid"
    )
    binding_defined: bool = False
    binding_dormant: bool = False
    literal_frozen: bool = False
    execution_surface_present: bool = False
    authorization_received: bool = False
    source_read_calls: Literal[0] = 0
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    target_write_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86ag_readiness(
    *,
    binding: M86AEDormantBindingContract,
    authorization: M86AFAuthorizationContract,
) -> M86AGReadinessSnapshot:
    if type(binding) is not M86AEDormantBindingContract:
        return M86AGReadinessSnapshot(failure_category="binding_contract_invalid")
    if not (
        binding.state == "DORMANT-NO-GO"
        and binding.real_binding_defined
        and not binding.real_binding_executed
        and binding.current_read_budget == 0
        and binding.target_write_budget == 0
    ):
        return M86AGReadinessSnapshot(failure_category="binding_contract_invalid")
    if type(authorization) is not M86AFAuthorizationContract:
        return M86AGReadinessSnapshot(
            failure_category="literal_contract_invalid",
            binding_defined=True,
            binding_dormant=True,
        )
    if not (
        authorization.state == "PREPARED-NOT-EXECUTABLE"
        and authorization.exact_key_count == 7
        and not authorization.execution_surface_present
        and not authorization.authorization_received
    ):
        return M86AGReadinessSnapshot(
            failure_category="literal_contract_invalid",
            binding_defined=True,
            binding_dormant=True,
        )
    return M86AGReadinessSnapshot(
        state="READY-TO-SHOW-AUTHORIZATION",
        failure_category="none",
        binding_defined=True,
        binding_dormant=True,
        literal_frozen=True,
    )


__all__ = ["M86AGReadinessSnapshot", "audit_m86ag_readiness"]
