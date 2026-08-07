"""Readiness M86-BD sin abrir dotenv ni mostrar el literal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_dotenv_probe_authorization import (
    M86BD_PUBLIC_CATEGORIES,
    M86BDAuthorizationContract,
)
from .bitrix_history_r0_m86_fixture_dotenv_bridge import (
    M86BCFixtureDotenvBridgeContract,
)


@dataclass(frozen=True)
class M86BDReadinessSnapshot:
    phase: Literal["M86-BD"] = "M86-BD"
    state: Literal["READY-TO-SHOW-DOTENV-AUTHORIZATION", "NO-GO"] = "NO-GO"
    bridge_fixture_only: bool = False
    categories_frozen: bool = False
    literal_prepared: bool = False
    literal_shown: Literal[False] = False
    authorization_received: Literal[False] = False
    linked_to_execution: Literal[False] = False
    real_path_bound: Literal[False] = False
    real_open_calls: Literal[0] = 0
    real_read_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86bd_readiness(
    *,
    bridge: M86BCFixtureDotenvBridgeContract,
    authorization: M86BDAuthorizationContract,
) -> M86BDReadinessSnapshot:
    if type(bridge) is not M86BCFixtureDotenvBridgeContract:
        return M86BDReadinessSnapshot()
    bridge_fixture_only = (
        bridge.state == "FIXTURE-ONLY-INERT"
        and bridge.source_must_be_injected
        and not bridge.real_path_factory_present
        and bridge.direct_bytearray_transfer
        and not bridge.real_execution_authorized
        and bridge.external_calls == 0
    )
    if type(authorization) is not M86BDAuthorizationContract:
        return M86BDReadinessSnapshot(bridge_fixture_only=bridge_fixture_only)
    categories_frozen = M86BD_PUBLIC_CATEGORIES == (
        "authorization_invalid",
        "source_open_unavailable",
        "source_transfer_unavailable",
        "candidate_not_fit",
        "composition_failed",
        "cleanup_ambiguous",
    )
    ready = (
        bridge_fixture_only
        and categories_frozen
        and authorization.state == "PREPARED-NOT-SHOWN"
        and not authorization.shown_to_person
        and not authorization.authorization_received
        and not authorization.linked_to_execution
        and authorization.single_open_budget == 0
        and authorization.current_real_read_budget == 0
        and authorization.external_calls == 0
    )
    return M86BDReadinessSnapshot(
        state="READY-TO-SHOW-DOTENV-AUTHORIZATION" if ready else "NO-GO",
        bridge_fixture_only=bridge_fixture_only,
        categories_frozen=categories_frozen,
        literal_prepared=True,
    )


__all__ = ["M86BDReadinessSnapshot", "audit_m86bd_readiness"]
