"""Contratos inertes para elegir la invocación única del owner OAuth R1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InvocationMode = Literal["WEBAPP_JOB", "INTERNAL_ENDPOINT"]


@dataclass(frozen=True)
class R1OAuthRefreshInvocationContract:
    mode: InvocationMode
    state: Literal["DESIGN_ONLY"] = "DESIGN_ONLY"
    owner_module: str = "bitrix_connector.r1_oauth_refresh_execution_owner"
    host: str = "nia-v365-next-api"
    managed_identity_required: Literal[True] = True
    exact_key_vault_read_max: Literal[1] = 1
    oauth_refresh_max: Literal[1] = 1
    persistence_verification_max: Literal[1] = 1
    retries: Literal[0] = 0
    bitrix_rest_calls: Literal[0] = 0
    messages: Literal[0] = 0
    deployment_calls: Literal[0] = 0
    route_mounts: Literal[0] = 0
    job_creations: Literal[0] = 0
    invocation_path: str = ""
    authentication: str = ""
    required_preflight: str = ""


def build_r1_oauth_refresh_invocation_contracts(
) -> tuple[R1OAuthRefreshInvocationContract, R1OAuthRefreshInvocationContract]:
    """Describe alternativas; no crea ruta, job ni recursos externos."""

    return (
        R1OAuthRefreshInvocationContract(
            mode="WEBAPP_JOB",
            invocation_path="platform_one_shot_job",
            authentication="platform_managed_identity",
            required_preflight=(
                "artifact_identity_and_managed_identity_confirmed"
            ),
        ),
        R1OAuthRefreshInvocationContract(
            mode="INTERNAL_ENDPOINT",
            invocation_path="/bitrix-connector/r1/oauth-refresh",
            authentication="application_validated_workload_identity",
            required_preflight=(
                "artifact_workload_identity_issuer_audience_client_and_managed_identity_confirmed"
            ),
        ),
    )


def contract_is_inert(contract: R1OAuthRefreshInvocationContract) -> bool:
    return bool(
        contract.state == "DESIGN_ONLY"
        and contract.managed_identity_required
        and contract.exact_key_vault_read_max == 1
        and contract.oauth_refresh_max == 1
        and contract.persistence_verification_max == 1
        and contract.retries == 0
        and contract.bitrix_rest_calls == 0
        and contract.messages == 0
        and contract.deployment_calls == 0
        and contract.route_mounts == 0
        and contract.job_creations == 0
        and bool(contract.invocation_path)
        and bool(contract.authentication)
        and bool(contract.required_preflight)
    )


__all__ = [
    "R1OAuthRefreshInvocationContract",
    "build_r1_oauth_refresh_invocation_contracts",
    "contract_is_inert",
]
