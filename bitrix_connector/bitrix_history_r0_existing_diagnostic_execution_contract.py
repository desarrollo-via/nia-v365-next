"""Contrato público M50, estático y no ejecutable, para un intento futuro."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExistingHistoryDiagnosticExecutionContract(BaseModel):
    """Describe límites verificables sin incluir frase, comando o dependencias."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M50"] = "M50"
    state: Literal["PREPARED"] = "PREPARED"
    reason: Literal[
        "bitrix_history_existing_execution_contract_prepared"
    ] = "bitrix_history_existing_execution_contract_prepared"

    objective_existing_history_shape_only: Literal[True] = True
    authentic_receipt_proven_by_this_contract: Literal[False] = False
    checklist_38_completion_authorized: Literal[False] = False
    human_message_required: Literal[False] = False
    waiting_message_allowed: Literal[False] = False

    separate_exact_authorization_required: Literal[True] = True
    authorization_present: Literal[False] = False
    authorization_phrase_defined: Literal[False] = False
    authorization_consumed_on_attempt: Literal[True] = True
    authorization_reusable: Literal[False] = False

    connector_barriers_required: Literal[True] = True
    protected_source_required: Literal[True] = True
    preflight_ready_required: Literal[True] = True
    resources_closed_required: Literal[True] = True
    no_oauth_refresh: Literal[True] = True
    no_retry: Literal[True] = True

    dialog_read_budget: Literal[1] = 1
    history_read_budget: Literal[1] = 1
    mutation_budget: Literal[0] = 0
    nia_call_budget: Literal[0] = 0
    message_send_budget: Literal[0] = 0
    wait_budget: Literal[0] = 0

    stop_on_authorization_invalid: Literal[True] = True
    stop_on_barrier_degraded: Literal[True] = True
    stop_on_source_or_oauth_failure: Literal[True] = True
    stop_on_preflight_failure: Literal[True] = True
    stop_on_history_failure: Literal[True] = True
    stop_on_close_failure: Literal[True] = True
    stop_on_ambiguous_output: Literal[True] = True

    output_status_only: Literal[True] = True
    output_safe_reason_only: Literal[True] = True
    output_m44_category_only: Literal[True] = True
    output_counters_only: Literal[True] = True
    output_barriers_only: Literal[True] = True
    output_message_content: Literal[False] = False
    output_session_identity: Literal[False] = False
    output_external_body: Literal[False] = False
    output_credentials: Literal[False] = False

    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    source_bound: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    source_open_authorized: Literal[False] = False
    bitrix_reads_authorized: Literal[False] = False

    dialog_read_calls: int = Field(default=0, ge=0, le=0)
    history_read_calls: int = Field(default=0, ge=0, le=0)
    mutation_calls: int = Field(default=0, ge=0, le=0)
    external_calls: int = Field(default=0, ge=0, le=0)
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_called: Literal[False] = False
    bitrix_written: Literal[False] = False


EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT = (
    ExistingHistoryDiagnosticExecutionContract()
)


__all__ = [
    "EXISTING_HISTORY_DIAGNOSTIC_EXECUTION_CONTRACT",
    "ExistingHistoryDiagnosticExecutionContract",
]
