"""Diseño M86-W del puerto sellado; no contiene implementación operativa."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_FORMAT,
    MAX_M84_BLOB_BYTES,
    WINDOWS_CREDENTIAL_BLOB_MAX_BYTES,
)


M86WFailureCategory = Literal[
    "none",
    "native_api_unavailable",
    "prior_state_unavailable",
    "prior_state_ambiguous",
    "prior_blob_invalid",
    "candidate_blob_invalid",
    "apply_failed",
    "apply_verification_failed",
    "rollback_delete_failed",
    "rollback_restore_failed",
    "rollback_verification_failed",
    "resource_close_failed",
    "cancelled",
]

M86W_FAILURE_CATEGORIES: tuple[M86WFailureCategory, ...] = (
    "none",
    "native_api_unavailable",
    "prior_state_unavailable",
    "prior_state_ambiguous",
    "prior_blob_invalid",
    "candidate_blob_invalid",
    "apply_failed",
    "apply_verification_failed",
    "rollback_delete_failed",
    "rollback_restore_failed",
    "rollback_verification_failed",
    "resource_close_failed",
    "cancelled",
)


@dataclass(frozen=True)
class M86WPriorStateProofContract:
    target_id: Literal["nia-next/bitrix-r1/protected-settings/v1"] = (
        M80_CREDENTIAL_TARGET_ID
    )
    accepted_states: tuple[str, str] = ("absent", "present")
    ambiguous_is_no_go: Literal[True] = True
    absence_requires_exact_native_not_found_classification: Literal[True] = True
    access_or_api_failure_is_not_absence: Literal[True] = True
    present_requires_successful_exact_target_read: Literal[True] = True
    present_backup_in_owned_bytearray: Literal[True] = True
    present_backup_never_parsed_for_public_output: Literal[True] = True
    public_blob_length_allowed: Literal[False] = False
    public_blob_digest_allowed: Literal[False] = False
    public_native_error_allowed: Literal[False] = False
    enumeration_budget: Literal[0] = 0
    backup_zeroized_in_finally: Literal[True] = True


@dataclass(frozen=True)
class M86WBranchBudget:
    prior_state: Literal["absent", "present"]
    exact_target_read_budget: int
    candidate_apply_budget: Literal[1] = 1
    restore_write_budget: int = 0
    delete_budget: int = 0
    enumeration_budget: Literal[0] = 0
    retry_budget: Literal[0] = 0

    def __post_init__(self) -> None:
        expected = {
            "absent": (3, 0, 1),
            "present": (3, 1, 0),
        }
        if (
            self.prior_state not in expected
            or (
                self.exact_target_read_budget,
                self.restore_write_budget,
                self.delete_budget,
            )
            != expected[self.prior_state]
        ):
            raise ValueError("m86w_branch_budget_invalid")


M86W_BRANCH_BUDGETS = (
    M86WBranchBudget(
        prior_state="absent",
        exact_target_read_budget=3,
        delete_budget=1,
    ),
    M86WBranchBudget(
        prior_state="present",
        exact_target_read_budget=3,
        restore_write_budget=1,
    ),
)


@dataclass(frozen=True)
class M86WSealedProvisioningPortContract:
    phase: Literal["M86-W"] = "M86-W"
    state: Literal["DESIGNED-INERT"] = "DESIGNED-INERT"
    reason: Literal["runtime_port_not_implemented"] = "runtime_port_not_implemented"
    target_id: Literal["nia-next/bitrix-r1/protected-settings/v1"] = (
        M80_CREDENTIAL_TARGET_ID
    )
    blob_format: Literal["ordered-name-length-value-v1"] = M84_BLOB_FORMAT
    local_parser_max_blob_bytes: int = MAX_M84_BLOB_BYTES
    native_max_blob_bytes: Literal[2560] = WINDOWS_CREDENTIAL_BLOB_MAX_BYTES
    native_blob_limit_verified: Literal[True] = True
    effective_max_blob_bytes: Literal[2560] = WINDOWS_CREDENTIAL_BLOB_MAX_BYTES
    native_limit_source: Literal[
        "https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw"
    ] = "https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw"
    prior_proof: M86WPriorStateProofContract = M86WPriorStateProofContract()
    branch_budgets: tuple[M86WBranchBudget, ...] = M86W_BRANCH_BUDGETS
    operation_sequence: tuple[str, ...] = (
        "classify_exact_prior_state_once",
        "retain_exact_prior_blob_only_if_present",
        "validate_candidate_against_local_and_verified_native_limits",
        "apply_candidate_once",
        "read_back_and_verify_candidate_exactly",
        "rollback_delete_if_prior_absent_or_restore_if_prior_present",
        "read_back_and_verify_exact_prior_state",
        "zeroize_all_owned_blobs_and_close_in_finally",
    )
    failure_categories: tuple[M86WFailureCategory, ...] = M86W_FAILURE_CATEGORIES
    public_failure_category_only: Literal[True] = True
    private_native_detail_retained: Literal[False] = False
    owned_candidate_zeroized_in_finally: Literal[True] = True
    owned_prior_backup_zeroized_in_finally: Literal[True] = True
    close_exactly_once: Literal[True] = True
    implementation_present: Literal[False] = False
    native_factory_present: Literal[False] = False
    real_value_source_bound: Literal[False] = False
    real_authorization_literals_present: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    operating_system_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            self.local_parser_max_blob_bytes != MAX_M84_BLOB_BYTES
            or self.native_max_blob_bytes != WINDOWS_CREDENTIAL_BLOB_MAX_BYTES
            or self.effective_max_blob_bytes != WINDOWS_CREDENTIAL_BLOB_MAX_BYTES
            or len(self.failure_categories) != len(set(self.failure_categories))
            or self.failure_categories[0] != "none"
            or tuple(item.prior_state for item in self.branch_budgets)
            != ("absent", "present")
            or len(self.operation_sequence) != len(set(self.operation_sequence))
        ):
            raise ValueError("m86w_sealed_port_contract_invalid")


def inspect_m86w_sealed_provisioning_port_contract(
) -> M86WSealedProvisioningPortContract:
    """Devuelve metadatos públicos constantes; no construye ningún puerto."""

    return M86WSealedProvisioningPortContract()


__all__ = [
    "M86WBranchBudget",
    "M86WFailureCategory",
    "M86WPriorStateProofContract",
    "M86WSealedProvisioningPortContract",
    "M86W_BRANCH_BUDGETS",
    "M86W_FAILURE_CATEGORIES",
    "inspect_m86w_sealed_provisioning_port_contract",
]
