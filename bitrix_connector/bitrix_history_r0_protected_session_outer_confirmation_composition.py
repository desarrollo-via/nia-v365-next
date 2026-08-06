"""Composición dormida M29 de la confirmación humana exterior R0."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_builder_composition import (
    DormantProtectedSessionBuilderCompositionSnapshot,
)
from .bitrix_history_r0_protected_session_human_boundary_contract import (
    PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT,
)


OUTER_CONFIRMATION_SCOPE = "outer-human-confirmation-contract-only"
OUTER_CONFIRMATION_ATTEMPT_LIMIT = 1
OUTER_CONFIRMATION_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class InjectedOuterHumanConfirmation:
    approved: bool = False
    scope: str = "none"


ConfirmationReader = Callable[[], Awaitable[InjectedOuterHumanConfirmation]]
TimeoutRunner = Callable[..., Awaitable[InjectedOuterHumanConfirmation]]


@dataclass(frozen=True)
class DormantProtectedSessionOuterConfirmationSnapshot:
    state: Literal["PREPARED", "CANCELLED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_outer_confirmation_not_started"
    builder_contract_consumed: bool = False
    activation_requested: bool = False
    confirmation_reader_bound: bool = False
    confirmation_attempt_limit: int = OUTER_CONFIRMATION_ATTEMPT_LIMIT
    confirmation_timeout_seconds: float = OUTER_CONFIRMATION_TIMEOUT_SECONDS
    confirmation_calls: int = 0
    confirmation_verified: bool = False
    human_boundary_prepared: bool = False
    builder_calls: int = 0
    source_calls: int = 0
    materializer_calls: int = 0
    external_calls: int = 0
    parser_real_enabled: bool = False
    builder_real_enabled: bool = False
    command_available: bool = False
    source_open_authorized: bool = False
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


async def fail_closed_outer_confirmation_reader(
) -> InjectedOuterHumanConfirmation:
    raise RuntimeError("protected_history_session_outer_confirmation_required")


def _builder_contract_is_exact(
    builder_contract: DormantProtectedSessionBuilderCompositionSnapshot,
) -> bool:
    return (
        type(builder_contract) is DormantProtectedSessionBuilderCompositionSnapshot
        and builder_contract.state == "PREPARED"
        and builder_contract.parser_contract_consumed is True
        and builder_contract.path_builder_bound is True
        and builder_contract.source_builder_bound is True
        and builder_contract.private_builder_bound is True
        and builder_contract.path_calls == 0
        and builder_contract.source_calls == 0
        and builder_contract.builder_calls == 0
        and builder_contract.materializer_calls == 0
        and builder_contract.parser_real_enabled is False
        and builder_contract.command_available is False
        and builder_contract.source_open_authorized is False
        and builder_contract.external_calls == 0
        and builder_contract.real_execution_authorized is False
        and builder_contract.message_request_authorized is False
    )


async def prepare_dormant_protected_session_outer_confirmation(
    *,
    builder_contract: DormantProtectedSessionBuilderCompositionSnapshot,
    activation_requested: bool = False,
    confirmation_reader: ConfirmationReader = fail_closed_outer_confirmation_reader,
    timeout_runner: TimeoutRunner = asyncio.wait_for,
) -> DormantProtectedSessionOuterConfirmationSnapshot:
    """Prueba la frontera con dobles; nunca habilita el owner ni la fuente real."""

    boundary = PROTECTED_HISTORY_SESSION_HUMAN_BOUNDARY_CONTRACT
    exact_contract = (
        _builder_contract_is_exact(builder_contract)
        and boundary.owner_call_limit == OUTER_CONFIRMATION_ATTEMPT_LIMIT
        and boundary.confirmation_read_limit == OUTER_CONFIRMATION_ATTEMPT_LIMIT
        and boundary.confirmation_timeout_seconds
        == OUTER_CONFIRMATION_TIMEOUT_SECONDS
        and boundary.real_source_configured is False
        and boundary.real_execution_authorized is False
        and boundary.message_request_authorized is False
        and callable(confirmation_reader)
        and callable(timeout_runner)
    )
    if not exact_contract:
        return DormantProtectedSessionOuterConfirmationSnapshot(
            reason="protected_history_session_outer_confirmation_contract_rejected"
        )
    if activation_requested is not True:
        return DormantProtectedSessionOuterConfirmationSnapshot(
            reason="protected_history_session_outer_confirmation_dormant_default",
            builder_contract_consumed=True,
            confirmation_reader_bound=True,
        )
    try:
        confirmation = await timeout_runner(
            confirmation_reader(), timeout=OUTER_CONFIRMATION_TIMEOUT_SECONDS
        )
        if (
            type(confirmation) is not InjectedOuterHumanConfirmation
            or confirmation.approved is not True
            or confirmation.scope != OUTER_CONFIRMATION_SCOPE
        ):
            raise TypeError("protected_history_session_outer_confirmation_rejected")
        return DormantProtectedSessionOuterConfirmationSnapshot(
            state="PREPARED",
            reason="protected_history_session_outer_confirmation_prepared_in_doubles",
            builder_contract_consumed=True,
            activation_requested=True,
            confirmation_reader_bound=True,
            confirmation_calls=1,
            confirmation_verified=True,
            human_boundary_prepared=True,
        )
    except asyncio.CancelledError:
        return DormantProtectedSessionOuterConfirmationSnapshot(
            state="CANCELLED",
            reason="protected_history_session_outer_confirmation_cancelled_terminal",
            builder_contract_consumed=True,
            activation_requested=True,
            confirmation_reader_bound=True,
            confirmation_calls=1,
        )
    except asyncio.TimeoutError:
        return DormantProtectedSessionOuterConfirmationSnapshot(
            reason="protected_history_session_outer_confirmation_timeout_terminal",
            builder_contract_consumed=True,
            activation_requested=True,
            confirmation_reader_bound=True,
            confirmation_calls=1,
        )
    except BaseException:
        return DormantProtectedSessionOuterConfirmationSnapshot(
            reason="protected_history_session_outer_confirmation_failed_safe",
            builder_contract_consumed=True,
            activation_requested=True,
            confirmation_reader_bound=True,
            confirmation_calls=1,
        )


__all__ = [
    "DormantProtectedSessionOuterConfirmationSnapshot",
    "InjectedOuterHumanConfirmation",
    "OUTER_CONFIRMATION_ATTEMPT_LIMIT",
    "OUTER_CONFIRMATION_SCOPE",
    "OUTER_CONFIRMATION_TIMEOUT_SECONDS",
    "fail_closed_outer_confirmation_reader",
    "prepare_dormant_protected_session_outer_confirmation",
]
