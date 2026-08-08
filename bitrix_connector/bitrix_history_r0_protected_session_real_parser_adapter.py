"""Adaptador dormido M27 para el contrato del parser real protegido R0."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal


PROTECTED_SESSION_REAL_CONFIRMATION = (
    "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ"
)
PROTECTED_SESSION_REAL_SOURCE = "local-dotenv"
PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS = 10.0
PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS = 300.0
PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE = "parser-contract-only"


@dataclass(frozen=True)
class InjectedProtectedSessionParserAuthorization:
    approved: bool = False
    scope: str = "none"


AuthorizationReader = Callable[
    [], Awaitable[InjectedProtectedSessionParserAuthorization]
]


@dataclass(frozen=True)
class DormantProtectedSessionRealParserSnapshot:
    state: Literal["PREPARED", "CANCELLED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_real_parser_not_started"
    activation_requested: bool = False
    exact_contract_valid: bool = False
    authorization_calls: int = 0
    authorization_verified: bool = False
    parser_contract_prepared: bool = False
    parser_real_enabled: bool = False
    command_available: bool = False
    builder_calls: int = 0
    source_calls: int = 0
    external_calls: int = 0
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


async def fail_closed_parser_authorization_reader(
) -> InjectedProtectedSessionParserAuthorization:
    raise RuntimeError("protected_history_session_parser_authorization_required")


async def prepare_dormant_protected_session_real_parser(
    *,
    confirm_code: str,
    protected_source: str,
    preflight_timeout_seconds: float,
    confirmation_timeout_seconds: float,
    activation_requested: bool = False,
    authorization_reader: AuthorizationReader = fail_closed_parser_authorization_reader,
) -> DormantProtectedSessionRealParserSnapshot:
    """Valida el contrato en memoria; nunca crea ni habilita un parser real."""

    exact_contract_valid = (
        confirm_code == PROTECTED_SESSION_REAL_CONFIRMATION
        and protected_source == PROTECTED_SESSION_REAL_SOURCE
        and preflight_timeout_seconds
        == PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS
        and confirmation_timeout_seconds
        == PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS
        and callable(authorization_reader)
    )
    if not exact_contract_valid:
        return DormantProtectedSessionRealParserSnapshot(
            reason="protected_history_session_real_parser_contract_rejected"
        )
    if activation_requested is not True:
        return DormantProtectedSessionRealParserSnapshot(
            reason="protected_history_session_real_parser_dormant_default",
            exact_contract_valid=True,
        )
    try:
        authorization = await authorization_reader()
        if (
            type(authorization) is not InjectedProtectedSessionParserAuthorization
            or authorization.approved is not True
            or authorization.scope
            != PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE
        ):
            raise TypeError("protected_history_session_parser_authorization_rejected")
        return DormantProtectedSessionRealParserSnapshot(
            state="PREPARED",
            reason="protected_history_session_real_parser_contract_prepared_in_doubles",
            activation_requested=True,
            exact_contract_valid=True,
            authorization_calls=1,
            authorization_verified=True,
            parser_contract_prepared=True,
        )
    except asyncio.CancelledError:
        return DormantProtectedSessionRealParserSnapshot(
            state="CANCELLED",
            reason="protected_history_session_real_parser_authorization_cancelled",
            activation_requested=True,
            exact_contract_valid=True,
            authorization_calls=1,
        )
    except BaseException:
        return DormantProtectedSessionRealParserSnapshot(
            reason="protected_history_session_real_parser_authorization_failed_safe",
            activation_requested=True,
            exact_contract_valid=True,
            authorization_calls=1,
        )


__all__ = [
    "DormantProtectedSessionRealParserSnapshot",
    "InjectedProtectedSessionParserAuthorization",
    "PROTECTED_SESSION_REAL_CONFIRMATION",
    "PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS",
    "PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE",
    "PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS",
    "PROTECTED_SESSION_REAL_SOURCE",
    "fail_closed_parser_authorization_reader",
    "prepare_dormant_protected_session_real_parser",
]
