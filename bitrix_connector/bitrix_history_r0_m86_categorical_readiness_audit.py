"""Auditoría M86-AP sin invocar la fábrica real ni mostrar el literal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_categorical_probe_authorization import (
    M86AOAuthorizationContract,
)
from .bitrix_history_r0_m86_dormant_real_categorical_owner import (
    M86ANDormantRealCategoricalOwner,
)


@dataclass(frozen=True)
class M86APReadinessSnapshot:
    phase: Literal["M86-AP"] = "M86-AP"
    state: Literal["READY-TO-SHOW-AUTHORIZATION", "NO-GO"] = "NO-GO"
    owner_dormant: bool = False
    real_factory_bound: bool = False
    literal_prepared: bool = False
    literal_shown: bool = False
    authorization_received: bool = False
    real_factory_calls: Literal[0] = 0
    real_read_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def audit_m86ap_readiness(
    *, owner: M86ANDormantRealCategoricalOwner,
    authorization: M86AOAuthorizationContract,
) -> M86APReadinessSnapshot:
    if type(owner) is not M86ANDormantRealCategoricalOwner:
        return M86APReadinessSnapshot()
    preview = owner.preview()
    if type(authorization) is not M86AOAuthorizationContract:
        return M86APReadinessSnapshot(
            owner_dormant=True,
            real_factory_bound=preview.real_factory_bound,
        )
    ready = (
        preview.state == "DORMANT-WAITING-AUTHORIZATION"
        and preview.current_real_read_budget == 0
        and authorization.state == "PREPARED-NOT-SHOWN"
        and not authorization.shown_to_person
        and not authorization.authorization_received
    )
    return M86APReadinessSnapshot(
        state="READY-TO-SHOW-AUTHORIZATION" if ready else "NO-GO",
        owner_dormant=True,
        real_factory_bound=preview.real_factory_bound,
        literal_prepared=True,
    )


__all__ = ["M86APReadinessSnapshot", "audit_m86ap_readiness"]
