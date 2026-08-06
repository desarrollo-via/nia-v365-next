"""Auditoría hermética M26 y delta congelado de activación R0."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_cli import ProtectedHistorySessionCliSnapshot
from .bitrix_history_r0_protected_session_cli_composition import (
    ProtectedHistorySessionOwnerCompositionPreviewSnapshot,
)


FixtureOwnerProbe = Callable[[], Awaitable[ProtectedHistorySessionCliSnapshot]]
CompositionPreview = Callable[[], ProtectedHistorySessionOwnerCompositionPreviewSnapshot]

PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA = (
    "accept_exact_frozen_real_parser_contract_after_independent_authorization",
    "compose_one_shot_allowlisted_source_and_private_session_builder",
    "bind_bounded_outer_human_confirmation_with_300_second_absolute_limit",
    "enable_command_only_after_hermetic_audit_and_independent_authorization",
)


@dataclass(frozen=True)
class ProtectedHistorySessionActivationDeltaContract:
    phase: str = "M26"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_activation_delta_unapplied"
    required_changes: tuple[str, ...] = PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA
    m24_fixture_owner_verified: bool = True
    m25_preview_verified: bool = True
    parser_real_enabled: bool = False
    real_session_builder_enabled: bool = False
    outer_confirmation_enabled: bool = False
    command_available: bool = False
    source_open_authorized: bool = False
    external_calls_authorized: bool = False
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


@dataclass(frozen=True)
class ProtectedHistorySessionHermeticAuditSnapshot:
    state: Literal["VERIFIED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_hermetic_audit_not_started"
    fixture_probe_calls: int = 0
    preview_calls: int = 0
    fixture_owner_received: bool = False
    fixture_private_state_cleared: bool = False
    preview_prepared: bool = False
    preview_all_calls_zero: bool = False
    parser_real_enabled: bool = False
    command_available: bool = False
    source_opened: bool = False
    external_calls: int = 0


async def audit_protected_history_session_activation_delta_once(
    *,
    fixture_owner_probe: FixtureOwnerProbe,
    composition_preview: CompositionPreview,
) -> ProtectedHistorySessionHermeticAuditSnapshot:
    """Audita M24-M25 sólo mediante dependencias inyectadas y redactadas."""

    if not callable(fixture_owner_probe) or not callable(composition_preview):
        return ProtectedHistorySessionHermeticAuditSnapshot(
            reason="protected_history_session_hermetic_audit_dependency_invalid"
        )
    fixture_probe_calls = 0
    preview_calls = 0
    try:
        fixture_probe_calls = 1
        fixture = await fixture_owner_probe()
        if type(fixture) is not ProtectedHistorySessionCliSnapshot:
            raise TypeError("protected_history_session_hermetic_fixture_invalid")
        preview_calls = 1
        preview = composition_preview()
        if type(preview) is not ProtectedHistorySessionOwnerCompositionPreviewSnapshot:
            raise TypeError("protected_history_session_hermetic_preview_invalid")
        call_fields = (
            "source_select_calls", "path_calls", "source_calls",
            "plan_launcher_calls", "materializer_calls",
            "inner_confirmation_calls", "outer_confirmation_calls",
            "gate_owner_calls", "cli_owner_calls", "external_calls",
        )
        all_calls_zero = all(getattr(preview, field) == 0 for field in call_fields)
        if (
            fixture.state != "RECEIVED"
            or fixture.private_state_cleared is not True
            or fixture.connector_locked_off is not True
            or fixture.persisted is not False
            or fixture.nia_called is not False
            or fixture.bitrix_written is not False
            or fixture.real_source_opened is not False
            or fixture.external_calls != 0
            or preview.state != "PREPARED"
            or preview.real_parser_blocked is not True
            or preview.command_available is not False
            or all_calls_zero is not True
        ):
            raise TypeError("protected_history_session_hermetic_barrier_degraded")
        return ProtectedHistorySessionHermeticAuditSnapshot(
            state="VERIFIED",
            reason="protected_history_session_hermetic_audit_verified",
            fixture_probe_calls=1,
            preview_calls=1,
            fixture_owner_received=True,
            fixture_private_state_cleared=True,
            preview_prepared=True,
            preview_all_calls_zero=True,
        )
    except BaseException:
        return ProtectedHistorySessionHermeticAuditSnapshot(
            reason="protected_history_session_hermetic_audit_failed_safe",
            fixture_probe_calls=fixture_probe_calls,
            preview_calls=preview_calls,
        )


PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA_CONTRACT = (
    ProtectedHistorySessionActivationDeltaContract()
)


__all__ = [
    "PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA",
    "PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA_CONTRACT",
    "ProtectedHistorySessionActivationDeltaContract",
    "ProtectedHistorySessionHermeticAuditSnapshot",
    "audit_protected_history_session_activation_delta_once",
]
