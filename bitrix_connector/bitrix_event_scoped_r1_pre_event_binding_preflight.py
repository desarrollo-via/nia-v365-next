"""Preflight hermético para un futuro montaje OAuth pre-evento R1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .bitrix_event_scoped_r1_cut_manifest import (
    M53_M86_CUT_EXPECTED_COUNT,
    M53_M86_CUT_EXPECTED_SHA256,
)
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


PRE_EVENT_BINDING_STRATEGY_SETTING = (
    "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY"
)
PRE_EVENT_BINDING_DEFAULT_STRATEGY: Literal["posterior"] = "posterior"
PRE_EVENT_BINDING_ALLOWED_STRATEGIES = ("posterior", "pre-event")
PRE_EVENT_BINDING_MAX_WINDOW_SECONDS = 600
PRE_EVENT_BINDING_PLANNED_PATHS = (
    "bitrix_connector/bitrix_event_scoped_r1_cut_manifest.py",
    "bitrix_connector/bitrix_event_scoped_r1_pre_event_binding.py",
    "bitrix_connector/bitrix_event_scoped_r1_pre_event_binding_preflight.py",
    "bitrix_connector/bitrix_event_scoped_r1_stage_plan.py",
    "bitrix_connector/config.py",
    "bitrix_connector/router.py",
    "tests/test_bitrix_connector.py",
    "tests/test_bitrix_event_scoped_r1_cut_manifest.py",
    "tests/test_bitrix_event_scoped_r1_pre_event_binding.py",
    "tests/test_bitrix_event_scoped_r1_pre_event_binding_preflight.py",
    "tests/test_bitrix_event_scoped_r1_stage_plan.py",
    "tests/test_bitrix_g0_entrypoint.py",
)
PRE_EVENT_BINDING_LOCAL_TRACE_PATHS = ("nia_next.md",)
PRE_EVENT_BINDING_ROLLBACK = (
    "restore-source-to-exact-pre-binding-commit",
    "set-participant-strategy-to-posterior",
    "verify-r1-posterior-and-connector-off-locked-inert",
)


@dataclass(frozen=True)
class PreEventBindingPreflightEvidence:
    protected_factory_dormant: bool
    router_binding_absent: bool
    mount_accepts_injected_factory: bool
    posterior_wrapper_mutually_excluded: bool
    protected_allowlist_exact: bool
    credential_read_budget_one: bool
    oauth_read_budget_one: bool
    refresh_budget_zero: bool
    retry_budget_zero: bool
    close_on_every_terminal_path: bool
    planned_default_is_posterior: bool
    planned_invalid_switch_fails_closed: bool
    planned_paths: tuple[str, ...]
    local_trace_paths: tuple[str, ...]
    candidate_path_count: int
    candidate_path_digest: str
    focal_tests_passed: bool
    full_tests_passed: bool
    dependency_cut_frozen: bool
    rollback_commit_sha: Optional[str] = None
    production_base_verified: bool = False


@dataclass(frozen=True)
class PreEventBindingPreflight:
    phase: Literal["M86-CR"] = "M86-CR"
    state: Literal["LOCAL-PREFLIGHT-PREPARED", "NO-GO"] = "NO-GO"
    exact_scope_verified: bool = False
    protected_contract_verified: bool = False
    dormant_default_verified: bool = False
    rollback_contract_defined: bool = False
    exact_deployment_rollback_ready: bool = False
    strategy_setting: str = PRE_EVENT_BINDING_STRATEGY_SETTING
    default_strategy: Literal["posterior"] = (
        PRE_EVENT_BINDING_DEFAULT_STRATEGY
    )
    maximum_window_seconds: Literal[600] = (
        PRE_EVENT_BINDING_MAX_WINDOW_SECONDS
    )
    protected_setting_count: Literal[7] = len(PROTECTED_SETTING_NAMES)
    planned_path_count: Literal[12] = len(PRE_EVENT_BINDING_PLANNED_PATHS)
    local_trace_path_count: Literal[1] = len(PRE_EVENT_BINDING_LOCAL_TRACE_PATHS)
    candidate_path_count: Literal[308] = M53_M86_CUT_EXPECTED_COUNT
    critical_binding_authorized: Literal[False] = False
    private_reads: Literal[0] = 0
    mongo_calls: Literal[0] = 0
    oauth_reads: Literal[0] = 0
    bitrix_calls: Literal[0] = 0
    participant_mutations: Literal[0] = 0
    messages: Literal[0] = 0
    persisted: Literal[False] = False


def _exact_sha(value: Optional[str]) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def audit_pre_event_binding_preflight(
    evidence: PreEventBindingPreflightEvidence,
) -> PreEventBindingPreflight:
    if type(evidence) is not PreEventBindingPreflightEvidence:
        return PreEventBindingPreflight()
    scope = bool(
        evidence.planned_paths == PRE_EVENT_BINDING_PLANNED_PATHS
        and evidence.local_trace_paths == PRE_EVENT_BINDING_LOCAL_TRACE_PATHS
        and evidence.candidate_path_count == M53_M86_CUT_EXPECTED_COUNT
        and evidence.candidate_path_digest == M53_M86_CUT_EXPECTED_SHA256
    )
    protected = bool(
        evidence.protected_factory_dormant
        and evidence.router_binding_absent
        and evidence.mount_accepts_injected_factory
        and evidence.posterior_wrapper_mutually_excluded
        and evidence.protected_allowlist_exact
        and evidence.credential_read_budget_one
        and evidence.oauth_read_budget_one
        and evidence.refresh_budget_zero
        and evidence.retry_budget_zero
        and evidence.close_on_every_terminal_path
    )
    dormant = bool(
        evidence.planned_default_is_posterior
        and evidence.planned_invalid_switch_fails_closed
    )
    tests = bool(
        evidence.focal_tests_passed
        and evidence.full_tests_passed
        and evidence.dependency_cut_frozen
    )
    prepared = scope and protected and dormant and tests
    exact_rollback = bool(
        prepared
        and evidence.production_base_verified
        and _exact_sha(evidence.rollback_commit_sha)
    )
    return PreEventBindingPreflight(
        state="LOCAL-PREFLIGHT-PREPARED" if prepared else "NO-GO",
        exact_scope_verified=scope,
        protected_contract_verified=protected,
        dormant_default_verified=dormant,
        rollback_contract_defined=prepared,
        exact_deployment_rollback_ready=exact_rollback,
    )


__all__ = [
    "PRE_EVENT_BINDING_ALLOWED_STRATEGIES",
    "PRE_EVENT_BINDING_DEFAULT_STRATEGY",
    "PRE_EVENT_BINDING_LOCAL_TRACE_PATHS",
    "PRE_EVENT_BINDING_MAX_WINDOW_SECONDS",
    "PRE_EVENT_BINDING_PLANNED_PATHS",
    "PRE_EVENT_BINDING_ROLLBACK",
    "PRE_EVENT_BINDING_STRATEGY_SETTING",
    "PreEventBindingPreflight",
    "PreEventBindingPreflightEvidence",
    "audit_pre_event_binding_preflight",
]
