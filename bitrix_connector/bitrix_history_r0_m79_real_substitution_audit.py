"""Auditoría M79 estática y paquete redactado de primera confirmación R1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class M79RealSubstitution:
    boundary: Literal[
        "protected_configuration_source",
        "stored_oauth_owner_without_refresh",
        "https_transport",
        "fresh_combined_preflight",
        "human_attention_boundary",
        "one_shot_command_owner",
    ]
    sealed_evidence: str
    real_candidate: str
    missing_binding: str
    ready: Literal[False] = False

    def __post_init__(self) -> None:
        if not self.sealed_evidence or not self.real_candidate or not self.missing_binding:
            raise ValueError("m79_real_substitution_invalid")


M79_REAL_SUBSTITUTIONS = (
    M79RealSubstitution(
        boundary="protected_configuration_source",
        sealed_evidence="m63_literal_and_allowlisted_source_contract_present",
        real_candidate="windows_credential_manager_preferred_but_not_integrated",
        missing_binding="approved_non_dotenv_protected_source_owner",
    ),
    M79RealSubstitution(
        boundary="stored_oauth_owner_without_refresh",
        sealed_evidence="m75_fixture_oauth_owner_verified_one_load_zero_refresh",
        real_candidate="PilotDiscoveryOAuthFactory",
        missing_binding="shared_real_stored_oauth_lifecycle_adapter_with_refresh_budget_zero",
    ),
    M79RealSubstitution(
        boundary="https_transport",
        sealed_evidence="m76_concrete_clients_verified_on_mock_transport",
        real_candidate="NiaClient_BitrixClient_BitrixHistoryR0Client",
        missing_binding="single_real_https_factory_for_four_closed_dependencies",
    ),
    M79RealSubstitution(
        boundary="fresh_combined_preflight",
        sealed_evidence="m68_combined_fixture_evidence_verified_once",
        real_candidate="existing_bot_openline_and_history_preflight_components",
        missing_binding="real_closed_probe_adapter_with_exact_four_read_budget",
    ),
    M79RealSubstitution(
        boundary="human_attention_boundary",
        sealed_evidence="m73_waiting_message_boundary_verified_by_fixture",
        real_candidate="project_notifier_and_explicit_human_signal",
        missing_binding="real_post_ready_attention_owner_without_message_capture",
    ),
    M79RealSubstitution(
        boundary="one_shot_command_owner",
        sealed_evidence="m78_single_sealed_owner_cleanup_and_reuse_rejection_verified",
        real_candidate="no_real_r1_command_is_available",
        missing_binding="single_source_bound_real_owner_and_non_reusable_command",
    ),
)


@dataclass(frozen=True)
class M79FirstConfirmationPackage:
    """Paquete público no ejecutable; no contiene el texto consumible M63."""

    state: Literal["NO-GO"] = "NO-GO"
    decision: Literal["DO-NOT-REQUEST"] = "DO-NOT-REQUEST"
    reason: str = "first_confirmation_blocked_by_source_conflict_and_six_real_bindings"
    object: str = "prepare_one_isolated_r1_roundtrip_only_for_the_controlled_chat"
    target_chat_id: Literal[78733] = 78733
    target_dialog_id: Literal["chat78733"] = "chat78733"
    target_line_id: Literal[13] = 13
    controlled_bot_id: Literal[373259] = 373259
    production_bot_id: Literal[245339] = 245339
    maximum_window_seconds: Literal[180] = 180
    mutation_budgets: tuple[tuple[str, int], ...] = (
        ("openline_config", 0),
        ("bot_registration", 0),
        ("route_assignment_or_binding", 0),
        ("wazzup", 0),
        ("mongo", 0),
    )
    read_and_call_budgets: tuple[tuple[str, int], ...] = (
        ("preflight_revision_read", 1),
        ("preflight_bot_list_read", 1),
        ("preflight_openline_config_read", 1),
        ("preflight_dialog_read", 1),
        ("baseline_history_read", 1),
        ("post_send_history_read", 1),
        ("nia_call", 1),
        ("bitrix_reply_send", 1),
        ("rollback_delete", 1),
        ("post_delete_history_read", 1),
        ("oauth_refresh", 0),
        ("retry", 0),
    )
    stop_criteria: tuple[str, ...] = (
        "missing_or_consumed_exact_authorization",
        "preflight_drift_or_ambiguity",
        "oauth_or_resource_failure",
        "history_or_single_candidate_failure",
        "nia_failure_or_invalid_response",
        "bitrix_send_failure_or_ambiguous_receipt",
        "resource_close_not_verified",
        "window_exceeded",
    )
    required_evidence: tuple[str, ...] = (
        "connector_locked_off_before_and_after",
        "only_chat78733_reached_nia_next",
        "one_nonempty_nia_next_response",
        "exact_send_receipt_message_id",
        "same_dialog_reply_verified",
        "no_persistence_and_no_other_chat_processed",
        "all_resources_closed",
    )
    exact_rollback: str = (
        "one_imbot_v2_chat_message_delete_for_bot_373259_using_only_the_exact_"
        "send_receipt_message_id_with_complete_true_then_one_same_session_"
        "history_read_verifying_absence"
    )
    contradiction: str = (
        "m63_first_literal_names_local_dotenv_while_active_m79_limit_forbids_"
        "opening_or_reading_dotenv"
    )
    substitution_count: Literal[6] = 6
    missing_substitution_count: Literal[6] = 6
    package_redacted: Literal[True] = True
    confirmation_text_included: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


@dataclass(frozen=True)
class M79RealSubstitutionAudit:
    phase: Literal["M79"] = "M79"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "sealed_chain_complete_but_real_substitutions_unbound"
    audited_chain: tuple[str, ...] = ("M63", "M68", "M73", "M75", "M76", "M77", "M78")
    substitutions: tuple[M79RealSubstitution, ...] = M79_REAL_SUBSTITUTIONS
    package: M79FirstConfirmationPackage = M79FirstConfirmationPackage()
    external_calls: Literal[0] = 0

    def __post_init__(self) -> None:
        expected = {
            "protected_configuration_source",
            "stored_oauth_owner_without_refresh",
            "https_transport",
            "fresh_combined_preflight",
            "human_attention_boundary",
            "one_shot_command_owner",
        }
        if (
            len(self.substitutions) != self.package.substitution_count
            or {item.boundary for item in self.substitutions} != expected
            or len({item.boundary for item in self.substitutions}) != len(self.substitutions)
            or sum(not item.ready for item in self.substitutions)
            != self.package.missing_substitution_count
        ):
            raise ValueError("m79_real_substitution_audit_invalid")


def audit_m79_real_substitutions() -> M79RealSubstitutionAudit:
    """Devuelve sólo evidencia pública fija; no abre fuentes ni crea recursos."""

    return M79RealSubstitutionAudit()


__all__ = [
    "M79FirstConfirmationPackage",
    "M79RealSubstitution",
    "M79RealSubstitutionAudit",
    "M79_REAL_SUBSTITUTIONS",
    "audit_m79_real_substitutions",
]
