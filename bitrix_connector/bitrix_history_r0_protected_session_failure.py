"""Categorías públicas y cerradas para la sesión R0 protegida."""

from __future__ import annotations

from .bitrix_history_r0_protected_preflight_composition import (
    PROTECTED_PREFLIGHT_FAILURE_CATEGORIES,
)
from .bitrix_history_r0_protected_reader_failure import (
    PROTECTED_READER_FAILURE_CATEGORIES,
)


PROTECTED_SESSION_FAILURE_CATEGORIES = frozenset(
    set(PROTECTED_PREFLIGHT_FAILURE_CATEGORIES)
    | set(PROTECTED_READER_FAILURE_CATEGORIES)
    | {
        "authorization_cancelled",
        "reader_no_go",
        "entrypoint_failed",
        "cleanup_failed",
        "coordinator_failed",
        "owner_failed",
        "cli_failed",
    }
)


def normalize_protected_session_failure_category(
    value: object,
    *,
    fallback: str,
) -> str:
    """Devuelve sólo categorías públicas conocidas."""

    if type(value) is str and value in PROTECTED_SESSION_FAILURE_CATEGORIES:
        return value
    if fallback not in PROTECTED_SESSION_FAILURE_CATEGORIES:
        raise ValueError("protected_session_failure_fallback_invalid")
    return fallback


__all__ = [
    "PROTECTED_SESSION_FAILURE_CATEGORIES",
    "normalize_protected_session_failure_category",
]
