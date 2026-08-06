"""Clasificación pública cerrada de fallos del lector R0 protegido."""

from __future__ import annotations

from .bitrix_history_r0_runner import BitrixHistoryR0Result


PROTECTED_READER_FAILURE_CATEGORIES = frozenset(
    {
        "reader_wait_timeout",
        "reader_barrier_degraded",
        "reader_window_or_anchor_invalid",
        "reader_dialog_unavailable",
        "reader_dialog_rejected",
        "reader_dialog_invalid",
        "reader_dialog_mismatch",
        "reader_dialog_drift",
        "reader_history_unavailable",
        "reader_history_rejected",
        "reader_history_invalid",
        "reader_history_envelope_invalid",
        "reader_history_collections_invalid",
        "reader_history_fields_invalid",
        "reader_history_too_large",
        "reader_message_identity_mismatch",
        "reader_candidate_count_invalid",
        "reader_controlled_message_mismatch",
        "reader_token_expired",
        "reader_resources_close_failed",
        "reader_failed",
        "reader_other_safe_failure",
    }
)

_FIXED_REASON_CATEGORIES = {
    "bitrix_history_wait_timeout": "reader_wait_timeout",
    "bitrix_history_barrier_degraded": "reader_barrier_degraded",
    "bitrix_history_window_invalid": "reader_window_or_anchor_invalid",
    "bitrix_history_anchor_invalid": "reader_window_or_anchor_invalid",
    "bitrix_history_session_identity_invalid": "reader_window_or_anchor_invalid",
    "bitrix_history_dialog_mismatch": "reader_dialog_mismatch",
    "bitrix_history_dialog_drift": "reader_dialog_drift",
    "bitrix_history_read_failed": "reader_history_unavailable",
    "bitrix_history_response_too_large": "reader_history_too_large",
    "bitrix_history_invalid_envelope": "reader_history_envelope_invalid",
    "bitrix_history_invalid_collections": "reader_history_collections_invalid",
    "bitrix_history_invalid_fields": "reader_history_fields_invalid",
    "bitrix_history_identity_mismatch": "reader_message_identity_mismatch",
    "bitrix_history_candidate_count_invalid": "reader_candidate_count_invalid",
    "bitrix_history_controlled_message_mismatch": (
        "reader_controlled_message_mismatch"
    ),
    "bitrix_history_token_expired": "reader_token_expired",
    "bitrix_history_resources_close_failed": "reader_resources_close_failed",
    "bitrix_history_runner_not_started": "reader_failed",
    "bitrix_history_runner_failed": "reader_failed",
}


def classify_protected_reader_failure(result: object) -> str:
    """Reduce el motivo interno a una categoría pública allowlisted."""

    if type(result) is not BitrixHistoryR0Result:
        return "reader_other_safe_failure"
    fixed = _FIXED_REASON_CATEGORIES.get(result.reason)
    if fixed is not None:
        return fixed
    history_phase = result.history_read_calls > 0
    if result.reason in {
        "bitrix_history_timeout",
        "bitrix_history_transport_error",
        "bitrix_history_read_unavailable",
    }:
        return (
            "reader_history_unavailable"
            if history_phase
            else "reader_dialog_unavailable"
        )
    if result.reason == "bitrix_history_read_rejected":
        return (
            "reader_history_rejected"
            if history_phase
            else "reader_dialog_rejected"
        )
    if result.reason == "bitrix_history_invalid_response":
        return (
            "reader_history_invalid"
            if history_phase
            else "reader_dialog_invalid"
        )
    return "reader_other_safe_failure"


__all__ = [
    "PROTECTED_READER_FAILURE_CATEGORIES",
    "classify_protected_reader_failure",
]
