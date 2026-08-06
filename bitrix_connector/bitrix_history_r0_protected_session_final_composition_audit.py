"""Auditoría hermética M30 de la composición dormida M27-M29."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_outer_confirmation_composition import (
    DormantProtectedSessionOuterConfirmationSnapshot,
)


@dataclass(frozen=True)
class ProtectedSessionFinalAuditCase:
    snapshot: DormantProtectedSessionOuterConfirmationSnapshot
    cleanup_verified: bool = False


AuditProbe = Callable[[], Awaitable[ProtectedSessionFinalAuditCase]]


@dataclass(frozen=True)
class ProtectedSessionFinalCompositionAuditContract:
    phase: str = "M30"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_final_composition_audited_dormant"
    probe_limit_per_case: int = 1
    confirmation_attempt_limit: int = 1
    confirmation_timeout_seconds: float = 300.0
    rejection_terminal: bool = True
    timeout_terminal: bool = True
    cancellation_terminal: bool = True
    cleanup_required: bool = True
    parser_real_enabled: bool = False
    builder_real_enabled: bool = False
    command_available: bool = False
    source_open_authorized: bool = False
    external_calls_authorized: bool = False
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


@dataclass(frozen=True)
class ProtectedSessionFinalCompositionAuditSnapshot:
    state: Literal["VERIFIED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_final_composition_audit_not_started"
    success_probe_calls: int = 0
    rejection_probe_calls: int = 0
    timeout_probe_calls: int = 0
    cancellation_probe_calls: int = 0
    success_verified: bool = False
    rejection_verified: bool = False
    timeout_verified: bool = False
    cancellation_verified: bool = False
    cleanup_verified: bool = False
    all_real_capabilities_false: bool = True
    source_opened: bool = False
    external_calls: int = 0


def _barriers_are_exact(
    snapshot: DormantProtectedSessionOuterConfirmationSnapshot,
) -> bool:
    return (
        type(snapshot) is DormantProtectedSessionOuterConfirmationSnapshot
        and snapshot.builder_contract_consumed is True
        and snapshot.activation_requested is True
        and snapshot.confirmation_reader_bound is True
        and snapshot.confirmation_attempt_limit == 1
        and snapshot.confirmation_timeout_seconds == 300.0
        and snapshot.confirmation_calls == 1
        and snapshot.builder_calls == 0
        and snapshot.source_calls == 0
        and snapshot.materializer_calls == 0
        and snapshot.external_calls == 0
        and snapshot.parser_real_enabled is False
        and snapshot.builder_real_enabled is False
        and snapshot.command_available is False
        and snapshot.source_open_authorized is False
        and snapshot.real_execution_authorized is False
        and snapshot.message_request_authorized is False
    )


def _case_is_exact(
    index: int,
    snapshot: DormantProtectedSessionOuterConfirmationSnapshot,
) -> bool:
    if index == 0:
        return (
            snapshot.state == "PREPARED"
            and snapshot.reason
            == "protected_history_session_outer_confirmation_prepared_in_doubles"
            and snapshot.confirmation_verified is True
            and snapshot.human_boundary_prepared is True
        )
    if index == 1:
        return (
            snapshot.state == "NO-GO"
            and snapshot.reason
            == "protected_history_session_outer_confirmation_failed_safe"
            and snapshot.confirmation_verified is False
        )
    if index == 2:
        return (
            snapshot.state == "NO-GO"
            and snapshot.reason
            == "protected_history_session_outer_confirmation_timeout_terminal"
        )
    return (
        index == 3
        and snapshot.state == "CANCELLED"
        and snapshot.reason
        == "protected_history_session_outer_confirmation_cancelled_terminal"
    )


async def audit_protected_session_final_composition_once(
    *,
    success_probe: AuditProbe,
    rejection_probe: AuditProbe,
    timeout_probe: AuditProbe,
    cancellation_probe: AuditProbe,
) -> ProtectedSessionFinalCompositionAuditSnapshot:
    """Consume una vez cada caso inyectado y publica sólo evidencia agregada."""

    probes = (success_probe, rejection_probe, timeout_probe, cancellation_probe)
    if not all(callable(probe) for probe in probes):
        return ProtectedSessionFinalCompositionAuditSnapshot(
            reason="protected_history_session_final_composition_dependency_invalid"
        )
    calls = [0, 0, 0, 0]
    try:
        for index, probe in enumerate(probes):
            calls[index] = 1
            case = await probe()
            if (
                type(case) is not ProtectedSessionFinalAuditCase
                or case.cleanup_verified is not True
                or not _barriers_are_exact(case.snapshot)
                or not _case_is_exact(index, case.snapshot)
            ):
                raise TypeError("protected_history_session_final_audit_case_invalid")
        return ProtectedSessionFinalCompositionAuditSnapshot(
            state="VERIFIED",
            reason="protected_history_session_final_composition_audit_verified",
            success_probe_calls=1,
            rejection_probe_calls=1,
            timeout_probe_calls=1,
            cancellation_probe_calls=1,
            success_verified=True,
            rejection_verified=True,
            timeout_verified=True,
            cancellation_verified=True,
            cleanup_verified=True,
        )
    except BaseException:
        return ProtectedSessionFinalCompositionAuditSnapshot(
            reason="protected_history_session_final_composition_audit_failed_safe",
            success_probe_calls=calls[0],
            rejection_probe_calls=calls[1],
            timeout_probe_calls=calls[2],
            cancellation_probe_calls=calls[3],
        )


PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT = (
    ProtectedSessionFinalCompositionAuditContract()
)


__all__ = [
    "PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT",
    "ProtectedSessionFinalAuditCase",
    "ProtectedSessionFinalCompositionAuditContract",
    "ProtectedSessionFinalCompositionAuditSnapshot",
    "audit_protected_session_final_composition_once",
]
