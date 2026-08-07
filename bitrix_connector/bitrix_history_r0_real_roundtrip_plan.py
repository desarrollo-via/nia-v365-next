"""Plan protegido M56, estatico y no ejecutable, del primer recorrido real."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProtectedRealRoundtripPlan(BaseModel):
    """Congela alcance y limites; no contiene clientes, secretos ni comandos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M56"] = "M56"
    reconciled_phase: Literal["M64"] = "M64"
    state: Literal["NO-GO"] = "NO-GO"
    reason: Literal[
        "real_roundtrip_plan_blocked_confirmations_and_real_binding_missing"
    ] = "real_roundtrip_plan_blocked_confirmations_and_real_binding_missing"

    objective_first_isolated_connection: Literal[True] = True
    target_dialog_id: Literal["chat78733"] = "chat78733"
    controlled_bot_id: Literal[373259] = 373259
    production_bot_id: Literal[245339] = 245339
    same_dialog_reply_required: Literal[True] = True
    minimum_filter_only: Literal[True] = True
    exact_text_hash_filter_deferred: Literal[True] = True
    exact_time_window_filter_deferred: Literal[True] = True

    production_bot_must_remain_untouched: Literal[True] = True
    openline_config_mutation_budget: Literal[0] = 0
    bot_registration_mutation_budget: Literal[0] = 0
    route_assignment_binding_mutation_budget: Literal[0] = 0
    wazzup_mutation_budget: Literal[0] = 0
    mongo_write_budget: Literal[0] = 0

    preflight_revision_read_budget: Literal[1] = 1
    preflight_bot_list_read_budget: Literal[1] = 1
    preflight_openline_config_read_budget: Literal[1] = 1
    preflight_dialog_read_budget: Literal[1] = 1
    baseline_history_read_budget: Literal[1] = 1
    post_send_history_read_budget: Literal[1] = 1
    nia_call_budget: Literal[1] = 1
    bitrix_reply_send_budget: Literal[1] = 1
    rollback_delete_call_budget: Literal[1] = 1
    post_delete_history_read_budget: Literal[1] = 1
    retry_budget: Literal[0] = 0
    maximum_window_seconds: Literal[180] = 180

    require_connector_locked_off_before_and_after: Literal[True] = True
    require_oauth_without_refresh: Literal[True] = True
    require_resources_closed: Literal[True] = True
    require_controlled_bot_present: Literal[True] = True
    require_production_bot_snapshot_exact: Literal[True] = True
    require_fresh_dialog_identity: Literal[True] = True
    require_single_human_candidate_after_baseline: Literal[True] = True
    require_nonempty_nia_response_within_limit: Literal[True] = True
    require_send_receipt_message_id: Literal[True] = True
    require_sent_message_in_same_dialog: Literal[True] = True

    stop_on_authorization_missing_or_consumed: Literal[True] = True
    stop_on_preflight_drift_or_ambiguity: Literal[True] = True
    stop_on_oauth_or_resource_failure: Literal[True] = True
    stop_on_history_or_candidate_failure: Literal[True] = True
    stop_on_nia_failure_or_invalid_response: Literal[True] = True
    stop_on_bitrix_send_failure_or_ambiguous_receipt: Literal[True] = True
    stop_without_retry: Literal[True] = True

    rollback_target_must_derive_from_send_receipt: Literal[True] = True
    rollback_must_remove_only_sent_reply: Literal[True] = True
    rollback_must_reverify_same_dialog_absence: Literal[True] = True
    rollback_method_locally_implemented: Literal[True] = True
    rollback_contract_locally_tested: Literal[True] = True
    rollback_verified_in_doubles: Literal[True] = True
    rollback_verified: Literal[False] = False
    execution_blocked_until_rollback_verified: Literal[True] = True

    first_precise_confirmation_required: Literal[True] = True
    second_precise_confirmation_required: Literal[True] = True
    first_precise_confirmation_present: Literal[False] = False
    second_precise_confirmation_present: Literal[False] = False
    m63_confirmation_drafts_consumable: Literal[False] = False
    generic_sp_authorizes_production_write: Literal[False] = False

    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    source_bound: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    human_message_required_now: Literal[False] = False
    attention_required_now: Literal[False] = False

    revision_read_calls: int = Field(default=0, ge=0, le=0)
    bot_list_read_calls: int = Field(default=0, ge=0, le=0)
    openline_config_read_calls: int = Field(default=0, ge=0, le=0)
    dialog_read_calls: int = Field(default=0, ge=0, le=0)
    history_read_calls: int = Field(default=0, ge=0, le=0)
    nia_calls: int = Field(default=0, ge=0, le=0)
    bitrix_write_calls: int = Field(default=0, ge=0, le=0)
    rollback_calls: int = Field(default=0, ge=0, le=0)
    external_calls: int = Field(default=0, ge=0, le=0)
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    actual_connection_proven: Literal[False] = False


def build_protected_real_roundtrip_plan() -> ProtectedRealRoundtripPlan:
    """Devuelve solamente el contrato inerte y bloqueado."""

    return ProtectedRealRoundtripPlan()


__all__ = [
    "ProtectedRealRoundtripPlan",
    "build_protected_real_roundtrip_plan",
]
