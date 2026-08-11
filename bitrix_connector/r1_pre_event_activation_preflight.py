"""Pure evaluator for sanitized R1 pre-event activation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


DEPLOYED_MERGE_SHA = "41ab2d5435cadf22db60574166d7eb29dd1dd57e"
DEPLOYED_TREE_SHA = "370a5b4e5b2b55420e0c918fa8dfc12c6bd42b30"
PROTECTED_TARGET_ID = "nia-next/bitrix-r1/protected-settings/v1"
PROTECTED_SOURCE_KIND = "azure-key-vault-exact-secret"
PROTECTED_SETTING_COUNT = 7
CONTROLLED_DEAL_ID = 614949
CONTROLLED_CHAT_ID = 78733
CONTROLLED_DIALOG_ID = "chat78733"
BOT_NIA_ID = 245339
BOT_NEXT_ID = 373259

R0_SETTING = "NIA_BITRIX_R0_BRIDGE_ENABLED"
R1_SETTING = "NIA_BITRIX_EVENT_R1_ENABLED"
STRATEGY_SETTING = "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY"
SWITCH_ORDER = (R0_SETTING, R1_SETTING, STRATEGY_SETTING)
EXPECTED_BASELINE_VALUES = {
    R0_SETTING: "false",
    R1_SETTING: "false",
    STRATEGY_SETTING: "posterior",
}


@dataclass(frozen=True)
class SanitizedSwitchBaseline:
    name: str
    present: bool
    value: Optional[str]


@dataclass(frozen=True)
class R1ActivationPreflightEvidence:
    deployed_sha: str
    deployed_tree: str
    workflow_success: bool
    dormant_health_verified: bool
    full_tests_passed: bool
    host_supports_protected_source: bool
    protected_source_kind: str
    protected_target_id: str
    protected_record_shape_verified: bool
    protected_setting_count: int
    credential_read_calls: int
    oauth_read_calls: int
    refresh_calls: int
    retry_calls: int
    resources_closed: bool
    review_auth_configured: bool
    switches: tuple[SanitizedSwitchBaseline, ...]
    deal_id: int
    chat_id: int
    dialog_id: str
    bot_nia_absent: bool
    bot_next_absent: bool
    secret_values_exposed: bool = False


@dataclass(frozen=True)
class R1ActivationPreflight:
    state: Literal["READY-FIRST-CONFIRMATION", "NO-GO"] = "NO-GO"
    deployment_verified: bool = False
    protected_source_verified: bool = False
    review_auth_verified: bool = False
    switch_baseline_verified: bool = False
    participant_baseline_verified: bool = False
    rollback_plan: tuple[str, ...] = ()
    activation_authorized: Literal[False] = False
    evaluator_private_reads: Literal[0] = 0
    evaluator_external_calls: Literal[0] = 0
    evaluator_mutations: Literal[0] = 0


def _switch_rollback(
    switches: tuple[SanitizedSwitchBaseline, ...],
) -> tuple[bool, tuple[str, ...]]:
    if len(switches) != len(SWITCH_ORDER):
        return False, ()
    plan: list[str] = []
    for expected_name, item in zip(SWITCH_ORDER, switches, strict=True):
        expected_value = EXPECTED_BASELINE_VALUES[expected_name]
        if type(item) is not SanitizedSwitchBaseline or item.name != expected_name:
            return False, ()
        if item.present:
            if item.value != expected_value:
                return False, ()
            plan.append(f"restore-value:{item.name}={item.value}")
        else:
            if item.value is not None:
                return False, ()
            plan.append(f"restore-absence:{item.name}")
    return True, tuple(plan)


def audit_r1_activation_preflight(
    evidence: R1ActivationPreflightEvidence,
) -> R1ActivationPreflight:
    if type(evidence) is not R1ActivationPreflightEvidence:
        return R1ActivationPreflight()

    deployment = bool(
        evidence.deployed_sha == DEPLOYED_MERGE_SHA
        and evidence.deployed_tree == DEPLOYED_TREE_SHA
        and evidence.workflow_success
        and evidence.dormant_health_verified
        and evidence.full_tests_passed
    )
    protected = bool(
        evidence.host_supports_protected_source
        and evidence.protected_source_kind == PROTECTED_SOURCE_KIND
        and evidence.protected_target_id == PROTECTED_TARGET_ID
        and evidence.protected_record_shape_verified
        and evidence.protected_setting_count == PROTECTED_SETTING_COUNT
        and evidence.credential_read_calls == 1
        and evidence.oauth_read_calls == 1
        and evidence.refresh_calls == 0
        and evidence.retry_calls == 0
        and evidence.resources_closed
        and not evidence.secret_values_exposed
    )
    switches, rollback_plan = _switch_rollback(evidence.switches)
    participants = bool(
        evidence.deal_id == CONTROLLED_DEAL_ID
        and evidence.chat_id == CONTROLLED_CHAT_ID
        and evidence.dialog_id == CONTROLLED_DIALOG_ID
        and evidence.bot_nia_absent
        and evidence.bot_next_absent
    )
    ready = bool(
        deployment
        and protected
        and evidence.review_auth_configured
        and switches
        and participants
    )
    return R1ActivationPreflight(
        state="READY-FIRST-CONFIRMATION" if ready else "NO-GO",
        deployment_verified=deployment,
        protected_source_verified=protected,
        review_auth_verified=evidence.review_auth_configured,
        switch_baseline_verified=switches,
        participant_baseline_verified=participants,
        rollback_plan=rollback_plan if ready else (),
    )


__all__ = [
    "BOT_NEXT_ID",
    "BOT_NIA_ID",
    "CONTROLLED_CHAT_ID",
    "CONTROLLED_DEAL_ID",
    "CONTROLLED_DIALOG_ID",
    "DEPLOYED_MERGE_SHA",
    "DEPLOYED_TREE_SHA",
    "EXPECTED_BASELINE_VALUES",
    "PROTECTED_SETTING_COUNT",
    "PROTECTED_SOURCE_KIND",
    "PROTECTED_TARGET_ID",
    "R0_SETTING",
    "R1ActivationPreflight",
    "R1ActivationPreflightEvidence",
    "R1_SETTING",
    "STRATEGY_SETTING",
    "SWITCH_ORDER",
    "SanitizedSwitchBaseline",
    "audit_r1_activation_preflight",
]
