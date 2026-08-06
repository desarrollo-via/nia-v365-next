"""Preflight protegido compuesto sólo con dependencias explícitamente inyectadas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .bitrix_history_r0_preflight_composition import (
    BitrixHistoryClientBuilder,
    StoredOAuthResourcesFactory,
    execute_stored_oauth_history_preflight_once,
)
from .bitrix_history_r0_protected_helper import (
    ProtectedHelperSnapshot,
    ProtectedHelperState,
    ProtectedValueSource,
)
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
    ProtectedSourceBuilder,
    execute_protected_dotenv_settings_once,
)
from .bitrix_history_r0_runner import BitrixHistoryR0Status
from .config import ConnectorSettings, load_settings
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource


PROTECTED_PREFLIGHT_FAILURE_CATEGORIES = frozenset(
    {
        "none",
        "protected_source_or_settings_failed",
        "barrier_degraded",
        "oauth_or_resources_failed",
        "oauth_token_expired",
        "dialog_read_unavailable",
        "dialog_read_rejected",
        "dialog_response_invalid",
        "dialog_identity_mismatch",
        "anchor_invalid",
        "resources_close_failed",
        "cancelled",
        "other_safe_failure",
    }
)
_OUTCOME_FAILURE_CATEGORIES = {
    "bitrix_history_barrier_degraded": "barrier_degraded",
    "bitrix_history_preflight_failed_safe": "oauth_or_resources_failed",
    "bitrix_history_token_expired": "oauth_token_expired",
    "bitrix_history_timeout": "dialog_read_unavailable",
    "bitrix_history_transport_error": "dialog_read_unavailable",
    "bitrix_history_read_unavailable": "dialog_read_unavailable",
    "bitrix_history_read_rejected": "dialog_read_rejected",
    "bitrix_history_invalid_response": "dialog_response_invalid",
    "bitrix_history_dialog_mismatch": "dialog_identity_mismatch",
    "bitrix_history_session_identity_invalid": "anchor_invalid",
    "bitrix_history_resources_close_failed": "resources_close_failed",
}


@dataclass(frozen=True)
class ProtectedPreflightSnapshot:
    """Salida pública cerrada; nunca contiene settings, token o ancla."""

    state: ProtectedHelperState = ProtectedHelperState.NO_GO
    reason: str = "protected_preflight_not_started"
    failure_category: str = "none"
    protected_source_opened: bool = False
    required_values_present: bool = False
    settings_operation_completed: bool = False
    resources_closed: bool = False
    source_read_calls: int = 0
    preflight_calls: int = 0
    dialog_read_calls: int = 0
    history_read_calls: int = 0
    mutation_calls: int = 0
    identity_diagnostic_available: bool = False
    chat_id_matches: bool = False
    dialog_id_matches: bool = False
    entity_type_matches: bool = False
    role_allowed: bool = False
    identity_mismatch_count: int = 0
    anchor_available: bool = False
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


def _public_snapshot(
    *,
    helper: ProtectedHelperSnapshot,
    outcome: BitrixHistoryR0PreflightOutcome | None,
    preflight_calls: int,
) -> ProtectedPreflightSnapshot:
    preflight_resources_closed = bool(
        outcome is None or outcome.result.resources_closed
    )
    resources_closed = helper.resources_closed and preflight_resources_closed
    ready = bool(
        helper.state is ProtectedHelperState.READY
        and outcome is not None
        and outcome.result.status is BitrixHistoryR0Status.READY
        and outcome.anchor_available
        and resources_closed
    )
    if ready:
        state = ProtectedHelperState.READY
        reason = "protected_preflight_ready"
        failure_category = "none"
    elif helper.state is ProtectedHelperState.CANCELLED:
        state = ProtectedHelperState.CANCELLED
        reason = "protected_preflight_cancelled"
        failure_category = "cancelled"
    elif not resources_closed:
        state = ProtectedHelperState.NO_GO
        reason = "protected_preflight_close_failed"
        failure_category = "resources_close_failed"
    elif outcome is not None:
        state = ProtectedHelperState.NO_GO
        reason = "protected_preflight_no_go"
        failure_category = _OUTCOME_FAILURE_CATEGORIES.get(
            outcome.result.reason,
            "other_safe_failure",
        )
    else:
        state = ProtectedHelperState.NO_GO
        reason = "protected_preflight_failed_safe"
        failure_category = "protected_source_or_settings_failed"

    result = outcome.result if outcome is not None else None
    diagnostic = (
        outcome.identity_diagnostic
        if failure_category == "dialog_identity_mismatch" and outcome is not None
        else None
    )
    return ProtectedPreflightSnapshot(
        state=state,
        reason=reason,
        failure_category=failure_category,
        protected_source_opened=helper.protected_source_opened,
        required_values_present=helper.required_values_present,
        settings_operation_completed=helper.operation_completed,
        resources_closed=resources_closed,
        source_read_calls=helper.source_read_calls,
        preflight_calls=preflight_calls,
        dialog_read_calls=result.dialog_read_calls if result is not None else 0,
        history_read_calls=result.history_read_calls if result is not None else 0,
        mutation_calls=result.mutation_calls if result is not None else 0,
        identity_diagnostic_available=diagnostic is not None,
        chat_id_matches=(diagnostic.chat_id_matches if diagnostic else False),
        dialog_id_matches=(diagnostic.dialog_id_matches if diagnostic else False),
        entity_type_matches=(
            diagnostic.entity_type_matches if diagnostic else False
        ),
        role_allowed=diagnostic.role_allowed if diagnostic else False,
        identity_mismatch_count=(diagnostic.mismatch_count if diagnostic else 0),
        anchor_available=ready,
        connector_locked_off=(
            result.connector_locked_off if result is not None else True
        ),
        persisted=result.persisted if result is not None else False,
        nia_called=result.nia_called if result is not None else False,
        bitrix_written=result.bitrix_written if result is not None else False,
    )


def classify_protected_preflight_failure(
    *,
    helper: ProtectedHelperSnapshot,
    outcome: object,
    preflight_calls: int,
) -> str:
    """Expone sólo la categoría allowlisted que ya usa el snapshot público."""

    if outcome is not None and type(outcome) is not BitrixHistoryR0PreflightOutcome:
        return "other_safe_failure"
    return _public_snapshot(
        helper=helper,
        outcome=outcome,
        preflight_calls=preflight_calls,
    ).failure_category


async def execute_protected_dotenv_preflight_once(
    *,
    dotenv_path: Path,
    resources_factory: StoredOAuthResourcesFactory,
    client_builder: BitrixHistoryClientBuilder,
    timeout_seconds: float = 10.0,
    settings_loader: ProtectedSettingsLoader = load_settings,
    source_builder: ProtectedSourceBuilder = AllowlistedDotenvSource,
) -> ProtectedPreflightSnapshot:
    """Ejecuta el preflight una vez sin seleccionar recursos reales por defecto."""

    outcome: BitrixHistoryR0PreflightOutcome | None = None
    preflight_calls = 0

    async def execute_preflight(settings: ConnectorSettings) -> None:
        nonlocal outcome, preflight_calls
        preflight_calls = 1
        outcome = await execute_stored_oauth_history_preflight_once(
            settings=settings,
            timeout_seconds=timeout_seconds,
            resources_factory=resources_factory,
            client_builder=client_builder,
        )
        if type(outcome) is not BitrixHistoryR0PreflightOutcome:
            raise TypeError("protected_preflight_outcome_invalid")

    helper = await execute_protected_dotenv_settings_once(
        dotenv_path=dotenv_path,
        operation=execute_preflight,
        settings_loader=settings_loader,
        source_builder=source_builder,
    )
    return _public_snapshot(
        helper=helper,
        outcome=outcome,
        preflight_calls=preflight_calls,
    )


__all__ = [
    "PROTECTED_PREFLIGHT_FAILURE_CATEGORIES",
    "ProtectedPreflightSnapshot",
    "classify_protected_preflight_failure",
    "execute_protected_dotenv_preflight_once",
]
