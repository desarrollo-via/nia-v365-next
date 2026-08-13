"""Pure preflight for the still-unbound protected probe invocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from .r1_key_vault_protected_probe_invocation_owner import (
    PROBE_ENDPOINT,
    REQUEST_TIMEOUT_SECONDS,
    REVIEW_TOKEN_NAME,
)


@dataclass(frozen=True)
class ProtectedProbeRealBindingPreflight:
    state: Literal["NO-GO-SOURCE-DECISION-REQUIRED"] = (
        "NO-GO-SOURCE-DECISION-REQUIRED"
    )
    reason: Literal["protected_review_token_source_unresolved"] = (
        "protected_review_token_source_unresolved"
    )
    review_token_name: Literal["NIA_BITRIX_REVIEW_TOKEN"] = REVIEW_TOKEN_NAME
    endpoint: Literal[
        "https://nia-v365-next-api-ekd4fza7e0fzevfd.canadacentral-01.azurewebsites.net/bitrix-connector/review/r1-key-vault-host-probe"
    ] = PROBE_ENDPOINT
    timeout_seconds: Literal[15] = REQUEST_TIMEOUT_SECONDS
    request_budget: Literal[1] = 1
    retry_budget: Literal[0] = 0
    redirect_budget: Literal[0] = 0
    existing_r1_target_id: Literal[
        "nia-next/bitrix-r1/protected-settings/v1"
    ] = M80_CREDENTIAL_TARGET_ID
    existing_r1_target_contains_review_token: Literal[False] = False
    source_target_id: None = None
    source_binding_ready: Literal[False] = False
    transport_binding_ready: Literal[True] = True
    execution_ready: Literal[False] = False
    source_opened: Literal[False] = False
    token_materialized: Literal[False] = False
    external_calls: Literal[0] = 0


def inspect_protected_probe_real_binding(
) -> ProtectedProbeRealBindingPreflight:
    if REVIEW_TOKEN_NAME in PROTECTED_SETTING_NAMES:
        raise RuntimeError("protected_review_token_unexpectedly_in_r1_blob")
    return ProtectedProbeRealBindingPreflight()


__all__ = [
    "ProtectedProbeRealBindingPreflight",
    "inspect_protected_probe_real_binding",
]
