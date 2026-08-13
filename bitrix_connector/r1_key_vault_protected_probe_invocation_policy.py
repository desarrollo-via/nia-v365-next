"""Pure, strict policy for the one-shot protected host-probe response."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any


EXPECTED_PACKAGES = {
    "azure-identity": "1.25.3",
    "azure-keyvault-secrets": "4.11.0",
    "aiohttp": "3.14.3",
}
EXPECTED_EVIDENCE_KEYS = {
    "schema",
    "packages",
    "setting_present",
    "setting_valid",
    "external_calls",
    "writes",
}


class ProtectedProbeInvocationState(str, Enum):
    VERIFIED_ABSENT = "HOST-RUNTIME-BASELINE-VERIFIED-SETTING-ABSENT"
    VERIFIED_PRESENT = "HOST-RUNTIME-BASELINE-VERIFIED-SETTING-PRESENT"
    AUTH_REJECTED_NOT_CONSUMED = "NO-GO-REVIEW-AUTH-NOT-CONSUMED"
    TOKEN_NOT_CONFIGURED_NOT_CONSUMED = "NO-GO-REVIEW-TOKEN-NOT-CONFIGURED"
    PROBE_NOT_BOUND_NOT_CONSUMED = "NO-GO-HOST-PROBE-NOT-BOUND"
    CONSUMED_FAILURE = "NO-GO-HOST-PROBE-CONSUMED-FAILURE"
    ALREADY_CONSUMED = "NO-GO-HOST-PROBE-ALREADY-CONSUMED"
    AMBIGUOUS_CONSUMPTION = "NO-GO-AMBIGUOUS-CONSUMPTION"
    NOT_SENT = "NO-GO-REQUEST-NOT-SENT"
    RESPONSE_DRIFT = "NO-GO-HOST-PROBE-RESPONSE-DRIFT"


def _exact_error(payload: Any, detail: str) -> bool:
    return (
        isinstance(payload, Mapping)
        and set(payload) == {"detail"}
        and payload.get("detail") == detail
    )


def _valid_success(payload: Any) -> bool:
    if not isinstance(payload, Mapping) or set(payload) != EXPECTED_EVIDENCE_KEYS:
        return False
    packages = payload.get("packages")
    if not isinstance(packages, Mapping) or dict(packages) != EXPECTED_PACKAGES:
        return False
    return (
        payload.get("schema") == "nia-next-r1-host-probe-v1"
        and type(payload.get("setting_present")) is bool
        and (
            (
                payload["setting_present"] is False
                and payload.get("setting_valid") is None
            )
            or (
                payload["setting_present"] is True
                and payload.get("setting_valid") is True
            )
        )
        and type(payload.get("external_calls")) is int
        and payload["external_calls"] == 0
        and type(payload.get("writes")) is int
        and payload["writes"] == 0
    )


def evaluate_protected_probe_result(
    *,
    status_code: int | None,
    payload: Any,
    request_may_have_reached_host: bool = True,
) -> ProtectedProbeInvocationState:
    """Classify only allowlisted evidence; never authorizes a retry."""

    if status_code is None:
        return (
            ProtectedProbeInvocationState.AMBIGUOUS_CONSUMPTION
            if request_may_have_reached_host
            else ProtectedProbeInvocationState.NOT_SENT
        )
    if status_code == 200 and _valid_success(payload):
        return (
            ProtectedProbeInvocationState.VERIFIED_PRESENT
            if payload["setting_present"]
            else ProtectedProbeInvocationState.VERIFIED_ABSENT
        )
    exact_errors = {
        (401, "review_unauthorized"): (
            ProtectedProbeInvocationState.AUTH_REJECTED_NOT_CONSUMED
        ),
        (503, "review_token_not_configured"): (
            ProtectedProbeInvocationState.TOKEN_NOT_CONFIGURED_NOT_CONSUMED
        ),
        (503, "host_probe_not_bound"): (
            ProtectedProbeInvocationState.PROBE_NOT_BOUND_NOT_CONSUMED
        ),
        (503, "host_probe_evidence_unavailable"): (
            ProtectedProbeInvocationState.CONSUMED_FAILURE
        ),
        (409, "host_probe_already_consumed"): (
            ProtectedProbeInvocationState.ALREADY_CONSUMED
        ),
    }
    for (expected_status, detail), state in exact_errors.items():
        if status_code == expected_status and _exact_error(payload, detail):
            return state
    return ProtectedProbeInvocationState.RESPONSE_DRIFT


__all__ = [
    "EXPECTED_PACKAGES",
    "ProtectedProbeInvocationState",
    "evaluate_protected_probe_result",
]
