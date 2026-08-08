"""Contrato puro M51 para verificar un recibo dentro del mismo historial."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExistingHistoryReceiptContract(BaseModel):
    """Congela selección privada sin ejecutar lecturas ni conservar contenido."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M51"] = "M51"
    state: Literal["PREPARED"] = "PREPARED"
    reason: Literal[
        "bitrix_history_existing_receipt_contract_prepared"
    ] = "bitrix_history_existing_receipt_contract_prepared"

    single_history_response_reused: Literal[True] = True
    second_history_read_allowed: Literal[False] = False
    shape_validation_precedes_selection: Literal[True] = True
    invalid_shape_stops_before_selection: Literal[True] = True

    multiple_history_entries_allowed: Literal[True] = True
    unrelated_entries_allowed: Literal[True] = True
    subsequent_existing_bot_reply_allowed: Literal[True] = True
    subsequent_existing_bot_reply_is_candidate: Literal[False] = False
    whole_history_single_candidate_required: Literal[False] = False
    controlled_candidate_count_required: Literal[1] = 1

    private_expected_text_or_hash_required: Literal[True] = True
    private_time_window_required: Literal[True] = True
    controlled_chat_identity_required: Literal[True] = True
    controlled_session_identity_required: Literal[True] = True
    candidate_timestamp_in_window_required: Literal[True] = True
    candidate_text_match_required: Literal[True] = True
    candidate_identity_consistent_required: Literal[True] = True

    current_bot_is_nia_next: Literal[False] = False
    existing_bot_activity_changes_nia_next_called: Literal[False] = False
    nia_next_call_budget: Literal[0] = 0
    message_send_budget: Literal[0] = 0
    wait_budget: Literal[0] = 0
    mutation_budget: Literal[0] = 0

    authentic_receipt_requires_unique_controlled_candidate: Literal[True] = True
    authentic_receipt_proven: Literal[False] = False
    checklist_38_completed: Literal[False] = False

    output_status_only: Literal[True] = True
    output_safe_reason_only: Literal[True] = True
    output_candidate_count_only: Literal[True] = True
    output_verification_booleans_only: Literal[True] = True
    output_message_content: Literal[False] = False
    output_expected_text_or_hash: Literal[False] = False
    output_time_window: Literal[False] = False
    output_session_identity: Literal[False] = False
    output_sender_identity: Literal[False] = False
    output_bot_reply_content: Literal[False] = False

    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    source_bound: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    human_message_required: Literal[False] = False
    waiting_message_allowed: Literal[False] = False

    dialog_read_calls: int = Field(default=0, ge=0, le=0)
    history_read_calls: int = Field(default=0, ge=0, le=0)
    candidate_count: int = Field(default=0, ge=0, le=0)
    mutation_calls: int = Field(default=0, ge=0, le=0)
    external_calls: int = Field(default=0, ge=0, le=0)
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


EXISTING_HISTORY_RECEIPT_CONTRACT = ExistingHistoryReceiptContract()


__all__ = [
    "EXISTING_HISTORY_RECEIPT_CONTRACT",
    "ExistingHistoryReceiptContract",
]
