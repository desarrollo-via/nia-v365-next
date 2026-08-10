"""Frozen real-operation budgets and exact dormant gate for R1 preflight."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .r1_pre_event_activation_evidence_collector import (
    R1ActivationEvidenceCollector,
)
from .r1_pre_event_activation_preflight import (
    BOT_NEXT_ID,
    BOT_NIA_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DEAL_ID,
    CONTROLLED_DIALOG_ID,
    PROTECTED_SETTING_COUNT,
    PROTECTED_SOURCE_KIND,
    PROTECTED_TARGET_ID,
    SWITCH_ORDER,
)
from .r1_pre_event_activation_real_binding import (
    R1ActivationDormantRealBinding,
    _R1ActivationRealBindingPermit,
)
from .r1_key_vault_exact_secret_backend import KEY_VAULT_SECRET_NAME


PREFLIGHT_AUTHORIZATION_LITERAL = (
    "AUTORIZO PREFLIGHT R1 SOLO LECTURA ONE-SHOT "
    "KEYVAULT-SECRET-EXACTO APPSETTINGS-3 CHAT78733 BOTS245339-373259"
)


@dataclass(frozen=True)
class R1ActivationRealOperationContract:
    deployment_external_reads: Literal[4] = 4
    deployment_retries: Literal[0] = 0
    deployment_mutations: Literal[0] = 0
    protected_target_id: str = PROTECTED_TARGET_ID
    protected_source_kind: str = PROTECTED_SOURCE_KIND
    protected_physical_secret_name: str = KEY_VAULT_SECRET_NAME
    protected_setting_count: int = PROTECTED_SETTING_COUNT
    credential_record_reads: Literal[1] = 1
    stored_oauth_reads: Literal[1] = 1
    oauth_refreshes: Literal[0] = 0
    protected_retries: Literal[0] = 0
    protected_resources_closed_before_return: Literal[True] = True
    switch_names: tuple[str, ...] = SWITCH_ORDER
    switch_exact_key_reads: Literal[3] = 3
    switch_enumerations: Literal[0] = 0
    exact_switch_reader_ready: Literal[True] = True
    participant_deal_id: int = CONTROLLED_DEAL_ID
    participant_chat_id: int = CONTROLLED_CHAT_ID
    participant_dialog_id: str = CONTROLLED_DIALOG_ID
    participant_bot_ids: tuple[int, int] = (BOT_NIA_ID, BOT_NEXT_ID)
    participant_reads: Literal[1] = 1
    participant_mutations: Literal[0] = 0
    participant_requires_oauth: Literal[True] = True
    compound_owner_ready: Literal[True] = True
    resources_closed_after_compound_read: Literal[True] = True
    linux_exact_secret_backend_ready: Literal[True] = True
    azure_sdk_dependencies_ready: bool = False
    managed_identity_configuration_verified: bool = False
    secret_output_budget: Literal[0] = 0
    total_mutation_budget: Literal[0] = 0


@dataclass(frozen=True)
class R1ActivationRealOperationReadiness:
    state: Literal["READY-EXACT-AUTHORIZATION", "NO-GO"] = "NO-GO"
    contracts_exact: bool = False
    protected_source_ready: bool = False
    switch_source_ready: bool = False
    oauth_ownership_ready: bool = False
    sanitized_output_only: bool = True
    gaps: tuple[str, ...] = ()
    activation_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    mutations: Literal[0] = 0


def audit_r1_real_operation_contract(
    contract: R1ActivationRealOperationContract,
) -> R1ActivationRealOperationReadiness:
    if type(contract) is not R1ActivationRealOperationContract:
        return R1ActivationRealOperationReadiness(
            sanitized_output_only=False,
            gaps=("contract_type_invalid",),
        )
    exact = bool(
        contract.deployment_external_reads == 4
        and contract.deployment_retries == 0
        and contract.deployment_mutations == 0
        and contract.protected_target_id == PROTECTED_TARGET_ID
        and contract.protected_source_kind == PROTECTED_SOURCE_KIND
        and contract.protected_physical_secret_name == KEY_VAULT_SECRET_NAME
        and contract.linux_exact_secret_backend_ready
        and contract.protected_setting_count == PROTECTED_SETTING_COUNT
        and contract.credential_record_reads == 1
        and contract.stored_oauth_reads == 1
        and contract.oauth_refreshes == 0
        and contract.protected_retries == 0
        and contract.protected_resources_closed_before_return
        and contract.switch_names == SWITCH_ORDER
        and contract.switch_exact_key_reads == 3
        and contract.switch_enumerations == 0
        and contract.participant_deal_id == CONTROLLED_DEAL_ID
        and contract.participant_chat_id == CONTROLLED_CHAT_ID
        and contract.participant_dialog_id == CONTROLLED_DIALOG_ID
        and contract.participant_bot_ids == (BOT_NIA_ID, BOT_NEXT_ID)
        and contract.participant_reads == 1
        and contract.participant_mutations == 0
        and contract.participant_requires_oauth
        and contract.secret_output_budget == 0
        and contract.total_mutation_budget == 0
    )
    switch_ready = bool(contract.exact_switch_reader_ready)
    oauth_ready = bool(
        contract.compound_owner_ready
        and contract.resources_closed_after_compound_read
    )
    protected_ready = bool(
        contract.linux_exact_secret_backend_ready
        and contract.azure_sdk_dependencies_ready
        and contract.managed_identity_configuration_verified
    )
    gaps: list[str] = []
    if not exact:
        gaps.append("operation_contract_drift")
    if not contract.azure_sdk_dependencies_ready:
        gaps.append("azure_sdk_dependencies_missing")
    if not contract.managed_identity_configuration_verified:
        gaps.append("managed_identity_configuration_unverified")
    if not switch_ready:
        gaps.append("exact_switch_source_missing")
    if not oauth_ready:
        gaps.append("oauth_ownership_gap")
    ready = exact and protected_ready and switch_ready and oauth_ready
    return R1ActivationRealOperationReadiness(
        state="READY-EXACT-AUTHORIZATION" if ready else "NO-GO",
        contracts_exact=exact,
        protected_source_ready=protected_ready,
        switch_source_ready=switch_ready,
        oauth_ownership_ready=oauth_ready,
        gaps=tuple(gaps),
    )


@dataclass(frozen=True)
class R1ActivationPreflightGateOutcome:
    state: Literal["COLLECTOR-MATERIALIZED", "NO-GO"] = "NO-GO"
    reason: str = "gate_not_run"
    collector: Optional[R1ActivationEvidenceCollector] = None
    authorization_consumed: bool = False
    collector_executed: Literal[False] = False
    activation_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    mutations: Literal[0] = 0


class R1ActivationPreflightAuthorizationGate:
    """One-shot gate; even success only materializes a dormant collector."""

    __slots__ = ("_binding", "_readiness", "_used")

    def __init__(
        self,
        *,
        binding: R1ActivationDormantRealBinding,
        readiness: R1ActivationRealOperationReadiness,
    ) -> None:
        if (
            type(binding) is not R1ActivationDormantRealBinding
            or type(readiness) is not R1ActivationRealOperationReadiness
        ):
            raise TypeError("r1_activation_preflight_gate_dependency_invalid")
        self._binding: Optional[R1ActivationDormantRealBinding] = binding
        self._readiness = readiness
        self._used = False

    def authorize_once(self, confirmation: str) -> R1ActivationPreflightGateOutcome:
        binding, self._binding = self._binding, None
        if self._used or binding is None:
            self._used = True
            return R1ActivationPreflightGateOutcome(reason="gate_reused")
        self._used = True
        if self._readiness.state != "READY-EXACT-AUTHORIZATION":
            return R1ActivationPreflightGateOutcome(
                reason="operation_contract_not_ready"
            )
        if confirmation != PREFLIGHT_AUTHORIZATION_LITERAL:
            return R1ActivationPreflightGateOutcome(
                reason="authorization_literal_mismatch"
            )
        collector = binding.build_after_gate_once(
            _R1ActivationRealBindingPermit()
        )
        return R1ActivationPreflightGateOutcome(
            state="COLLECTOR-MATERIALIZED",
            reason="exact_authorization_consumed",
            collector=collector,
            authorization_consumed=True,
        )


def current_r1_real_operation_readiness() -> R1ActivationRealOperationReadiness:
    return audit_r1_real_operation_contract(
        R1ActivationRealOperationContract()
    )


__all__ = [
    "PREFLIGHT_AUTHORIZATION_LITERAL",
    "R1ActivationPreflightAuthorizationGate",
    "R1ActivationPreflightGateOutcome",
    "R1ActivationRealOperationContract",
    "R1ActivationRealOperationReadiness",
    "audit_r1_real_operation_contract",
    "current_r1_real_operation_readiness",
]
