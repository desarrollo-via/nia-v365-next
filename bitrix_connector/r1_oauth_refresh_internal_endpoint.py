"""Adaptador inerte de la futura ruta interna del owner OAuth R1."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .r1_oauth_refresh_execution_owner import (
    R1OAuthRefreshSnapshot,
    R1_OAUTH_REFRESH_CONFIRMATION,
    R1_OAUTH_REFRESH_OWNER_MODULE,
)
from .r1_oauth_refresh_workload_identity_auth import (
    R1InternalWorkloadIdentityPolicy,
    R1ValidatedWorkloadIdentity,
    validate_r1_internal_workload_identity_once,
)


R1_OAUTH_REFRESH_INTERNAL_PATH = "/bitrix-connector/r1/oauth-refresh"


@dataclass(frozen=True)
class R1InternalInvocationPrincipal:
    """Principal derivado por plataforma; nunca se recibe desde el cliente."""

    subject: str
    authenticated_at: datetime


@dataclass(frozen=True)
class R1OAuthRefreshInternalEndpointPlan:
    state: Literal["LOCAL_READY"] = "LOCAL_READY"
    path: str = R1_OAUTH_REFRESH_INTERNAL_PATH
    owner_module: str = R1_OAUTH_REFRESH_OWNER_MODULE
    authentication: Literal["APPLICATION_VALIDATED_WORKLOAD_IDENTITY"] = (
        "APPLICATION_VALIDATED_WORKLOAD_IDENTITY"
    )
    client_actor_accepted: Literal[False] = False
    key_vault_reads_max: Literal[1] = 1
    oauth_refreshes_max: Literal[1] = 1
    persistence_verifications_max: Literal[1] = 1
    retries: Literal[0] = 0
    route_mounts: Literal[0] = 0
    deployment_calls: Literal[0] = 0
    external_calls: Literal[0] = 0


def build_r1_oauth_refresh_internal_endpoint_plan(
) -> R1OAuthRefreshInternalEndpointPlan:
    """Describe la ruta futura sin crear un router ni cargar configuración."""

    return R1OAuthRefreshInternalEndpointPlan()


EndpointExecutor = Callable[[], Awaitable[R1OAuthRefreshSnapshot]]


async def invoke_injected_r1_oauth_refresh_internal_endpoint_once(
    plan: R1OAuthRefreshInternalEndpointPlan,
    *,
    principal: R1InternalInvocationPrincipal | None,
    confirmation: str,
    executor: EndpointExecutor,
) -> R1OAuthRefreshSnapshot:
    """Prueba el gate interno con dobles; no monta ni ejecuta una ruta real."""

    if (
        type(plan) is not R1OAuthRefreshInternalEndpointPlan
        or type(principal) is not R1InternalInvocationPrincipal
        or not principal.subject.strip()
        or confirmation != R1_OAUTH_REFRESH_CONFIRMATION
        or not callable(executor)
    ):
        return R1OAuthRefreshSnapshot(reason="r1_internal_endpoint_rejected")
    snapshot = await executor()
    if type(snapshot) is not R1OAuthRefreshSnapshot:
        return R1OAuthRefreshSnapshot(reason="r1_internal_endpoint_result_invalid")
    return snapshot


async def authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once(
    plan: R1OAuthRefreshInternalEndpointPlan,
    *,
    policy: R1InternalWorkloadIdentityPolicy,
    identity: R1ValidatedWorkloadIdentity | None,
    now: datetime,
    confirmation: str,
    executor: EndpointExecutor,
) -> R1OAuthRefreshSnapshot:
    """Compone el gate de identidad validada sin montar una ruta HTTP."""

    if not validate_r1_internal_workload_identity_once(
        policy, identity, now=now
    ):
        return R1OAuthRefreshSnapshot(reason="r1_internal_identity_rejected")
    assert identity is not None
    return await invoke_injected_r1_oauth_refresh_internal_endpoint_once(
        plan,
        principal=R1InternalInvocationPrincipal(
            subject=identity.subject,
            authenticated_at=identity.authenticated_at,
        ),
        confirmation=confirmation,
        executor=executor,
    )


__all__ = [
    "R1InternalInvocationPrincipal",
    "R1OAuthRefreshInternalEndpointPlan",
    "R1_OAUTH_REFRESH_INTERNAL_PATH",
    "authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once",
    "build_r1_oauth_refresh_internal_endpoint_plan",
    "invoke_injected_r1_oauth_refresh_internal_endpoint_once",
]
