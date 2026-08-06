"""Diseño M80 inerte para Credential Manager y el owner R1 real único."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


M80_CREDENTIAL_TARGET_ID = "nia-next/bitrix-r1/protected-settings/v1"

M80_M63_SOURCE_CLAUSE_REPLACEMENT = (
    "Autorizo una sola lectura interna protegida del registro exacto "
    "nia-next/bitrix-r1/protected-settings/v1 en el Administrador de "
    "credenciales de Windows, sin enumerar otras credenciales, para transferir "
    "únicamente NIA_BITRIX_DOMAIN, NIA_BITRIX_MEMBER_ID, "
    "NIA_BITRIX_CLIENT_ID, NIA_BITRIX_CLIENT_SECRET, NIA_BITRIX_MONGO_URI, "
    "NIA_BITRIX_MONGO_DB y NIA_BITRIX_INSTALLATIONS_COLLECTION, sin mostrar, "
    "copiar, transcribir, contar, validar ni registrar sus valores; el owner "
    "debe cerrar y limpiar todos los buffers en finally, sin fallback a dotenv "
    "ni al entorno del proceso;"
)


@dataclass(frozen=True)
class M80WindowsCredentialSourceContract:
    source_kind: Literal["windows-generic-credential"] = "windows-generic-credential"
    target_id: Literal["nia-next/bitrix-r1/protected-settings/v1"] = (
        M80_CREDENTIAL_TARGET_ID
    )
    allowed_names: tuple[str, ...] = PROTECTED_SETTING_NAMES
    credential_record_read_budget: Literal[1] = 1
    helper_buffer_read_budget: Literal[7] = 7
    credential_enumeration_budget: Literal[0] = 0
    credential_write_budget: Literal[0] = 0
    credential_delete_budget: Literal[0] = 0
    process_environment_read_budget: Literal[0] = 0
    dotenv_read_budget: Literal[0] = 0
    fallback_allowed: Literal[False] = False
    values_leave_owner_memory: Literal[False] = False
    public_individual_presence_flags: Literal[False] = False
    aggregate_ready_or_no_go_only: Literal[True] = True
    close_and_zeroize_in_finally: Literal[True] = True
    one_shot: Literal[True] = True
    satisfies_m63_allowlist_by_contract: Literal[True] = True
    changes_external_budgets: Literal[False] = False
    implementation_present: Literal[False] = False
    dependency_declared: Literal[False] = False
    credential_record_verified: Literal[False] = False
    source_opened: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            self.allowed_names != PROTECTED_SETTING_NAMES
            or len(self.allowed_names) != self.helper_buffer_read_budget
            or len(set(self.allowed_names)) != self.helper_buffer_read_budget
        ):
            raise ValueError("m80_windows_credential_contract_invalid")


@dataclass(frozen=True)
class M80RealOwnerBinding:
    boundary: Literal[
        "protected_configuration_source",
        "stored_oauth_owner_without_refresh",
        "https_transport",
        "fresh_combined_preflight",
        "human_attention_boundary",
        "one_shot_command_owner",
    ]
    required_adapter: str
    owner_rule: str
    call_budget: int
    retry_budget: Literal[0] = 0
    implementation_present: Literal[False] = False

    def __post_init__(self) -> None:
        if not self.required_adapter or not self.owner_rule or self.call_budget < 0:
            raise ValueError("m80_real_owner_binding_invalid")


M80_REAL_OWNER_BINDINGS = (
    M80RealOwnerBinding(
        boundary="protected_configuration_source",
        required_adapter="WindowsCredentialProtectedValueSource",
        owner_rule="one_exact_target_one_fetch_no_enumeration_close_and_zeroize",
        call_budget=1,
    ),
    M80RealOwnerBinding(
        boundary="stored_oauth_owner_without_refresh",
        required_adapter="StoredOAuthNoRefreshResourceOwner",
        owner_rule="one_stored_access_token_read_refresh_method_unreachable_close_once",
        call_budget=1,
    ),
    M80RealOwnerBinding(
        boundary="https_transport",
        required_adapter="RealR1HttpsDependencyFactory",
        owner_rule="four_lazily_built_dependencies_https_only_timeout_ten_close_each_once",
        call_budget=4,
    ),
    M80RealOwnerBinding(
        boundary="fresh_combined_preflight",
        required_adapter="RealCombinedR1PreflightAdapter",
        owner_rule="four_exact_reads_then_private_anchor_no_history_read",
        call_budget=4,
    ),
    M80RealOwnerBinding(
        boundary="human_attention_boundary",
        required_adapter="RealWaitingMessageAttentionOwner",
        owner_rule="emit_attention_only_after_ready_then_accept_one_explicit_signal",
        call_budget=1,
    ),
    M80RealOwnerBinding(
        boundary="one_shot_command_owner",
        required_adapter="SingleRealR1ProcessOwner",
        owner_rule="consume_exact_authorizations_once_stop_without_retry_close_all_in_finally",
        call_budget=1,
    ),
)


@dataclass(frozen=True)
class M80OwnerSequenceContract:
    sequence: tuple[str, ...] = (
        "consume_first_exact_confirmation",
        "load_protected_settings_once",
        "load_stored_oauth_once_without_refresh",
        "run_fresh_combined_preflight_once",
        "consume_manual_removal_evidence",
        "consume_second_exact_confirmation",
        "emit_waiting_message_attention_and_accept_one_signal",
        "run_exact_same_chat_roundtrip_once",
        "rollback_exact_send_receipt_if_required",
        "close_every_private_resource_in_finally",
    )
    maximum_window_seconds: Literal[180] = 180
    retry_budget: Literal[0] = 0
    oauth_refresh_budget: Literal[0] = 0
    other_chat_budget: Literal[0] = 0
    persistence_budget: Literal[0] = 0
    production_configuration_mutation_budget: Literal[0] = 0


@dataclass(frozen=True)
class M80DesignAudit:
    phase: Literal["M80"] = "M80"
    state: Literal["DESIGNED-NO-GO"] = "DESIGNED-NO-GO"
    reason: str = "credential_contract_capable_but_real_owner_not_implemented"
    credential_decision: Literal["CAPABLE-BY-CONTRACT"] = "CAPABLE-BY-CONTRACT"
    source_contract: M80WindowsCredentialSourceContract = (
        M80WindowsCredentialSourceContract()
    )
    owner_bindings: tuple[M80RealOwnerBinding, ...] = M80_REAL_OWNER_BINDINGS
    owner_sequence: M80OwnerSequenceContract = M80OwnerSequenceContract()
    m63_source_clause_delta_ready: Literal[True] = True
    m63_modified: Literal[False] = False
    missing_implementation_count: Literal[6] = 6
    first_confirmation_decision: Literal["DO-NOT-REQUEST"] = "DO-NOT-REQUEST"
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
            len(self.owner_bindings) != self.missing_implementation_count
            or {item.boundary for item in self.owner_bindings} != expected
            or sum(not item.implementation_present for item in self.owner_bindings)
            != self.missing_implementation_count
            or any(item.retry_budget != 0 for item in self.owner_bindings)
        ):
            raise ValueError("m80_design_audit_invalid")


def design_m80_windows_credential_owner() -> M80DesignAudit:
    """Devuelve sólo el diseño público; no consulta fuentes ni crea clientes."""

    return M80DesignAudit()


__all__ = [
    "M80_CREDENTIAL_TARGET_ID",
    "M80_M63_SOURCE_CLAUSE_REPLACEMENT",
    "M80_REAL_OWNER_BINDINGS",
    "M80DesignAudit",
    "M80OwnerSequenceContract",
    "M80RealOwnerBinding",
    "M80WindowsCredentialSourceContract",
    "design_m80_windows_credential_owner",
]
