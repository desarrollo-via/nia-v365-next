"""Auditoría M86-BB inerte de proveedores capaces de alimentar M86-AZ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class M86BBProviderCandidate:
    source_kind: Literal[
        "windows-credential-target",
        "allowlisted-process-environment",
        "local-dotenv",
    ]
    adapter_present: Literal[True]
    current_real_state: Literal[
        "HISTORICAL-NO-GO",
        "NOT-INSPECTED",
    ]
    fixture_bridge_eligible: bool
    real_use_requires_new_exact_authorization: Literal[True] = True
    values_read_now: Literal[False] = False


M86BB_PROVIDER_CANDIDATES = (
    M86BBProviderCandidate(
        source_kind="windows-credential-target",
        adapter_present=True,
        current_real_state="HISTORICAL-NO-GO",
        fixture_bridge_eligible=False,
    ),
    M86BBProviderCandidate(
        source_kind="allowlisted-process-environment",
        adapter_present=True,
        current_real_state="HISTORICAL-NO-GO",
        fixture_bridge_eligible=False,
    ),
    M86BBProviderCandidate(
        source_kind="local-dotenv",
        adapter_present=True,
        current_real_state="NOT-INSPECTED",
        fixture_bridge_eligible=True,
    ),
)


@dataclass(frozen=True)
class M86BBProtectedProviderAudit:
    phase: Literal["M86-BB"] = "M86-BB"
    state: Literal["READY-TO-BUILD-FIXTURE-DOTENV-BRIDGE"] = (
        "READY-TO-BUILD-FIXTURE-DOTENV-BRIDGE"
    )
    candidates: tuple[M86BBProviderCandidate, ...] = M86BB_PROVIDER_CANDIDATES
    selected_fixture_bridge: Literal["local-dotenv"] = "local-dotenv"
    selected_real_provider: Literal["none"] = "none"
    credential_manager_historical_result: Literal[
        "protected_source_record_unavailable"
    ] = "protected_source_record_unavailable"
    process_environment_historical_result: Literal[
        "source_open_unavailable"
    ] = "source_open_unavailable"
    dotenv_real_state: Literal["not_inspected"] = "not_inspected"
    dotenv_exact_authorization_required_before_real_open: Literal[True] = True
    fixture_only_next: Literal[True] = True
    values_read: Literal[False] = False
    files_opened: Literal[0] = 0
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            tuple(item.source_kind for item in self.candidates)
            != (
                "windows-credential-target",
                "allowlisted-process-environment",
                "local-dotenv",
            )
            or sum(item.fixture_bridge_eligible for item in self.candidates) != 1
            or not self.candidates[-1].fixture_bridge_eligible
            or self.selected_fixture_bridge != self.candidates[-1].source_kind
        ):
            raise ValueError("m86bb_provider_audit_invalid")


def inspect_m86bb_protected_provider_audit() -> M86BBProtectedProviderAudit:
    """Devuelve sólo evidencia constante; no construye ni abre proveedores."""

    return M86BBProtectedProviderAudit()


__all__ = [
    "M86BB_PROVIDER_CANDIDATES",
    "M86BBProtectedProviderAudit",
    "M86BBProviderCandidate",
    "inspect_m86bb_protected_provider_audit",
]
