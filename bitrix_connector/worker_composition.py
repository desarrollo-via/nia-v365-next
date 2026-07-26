"""Composición inyectable de workers, sin bucle ni clientes HTTP propios."""

from __future__ import annotations

from dataclasses import dataclass

from .bitrix_dispatch import (
    BitrixDispatchWorkerHandler,
    BitrixDispatchWorkerStore,
    BitrixMessageSender,
)
from .mode_policy import (
    ExternalCallPolicyProvider,
    current_external_call_policy,
)
from .nia_dispatch import (
    NiaDispatchWorkerHandler,
    NiaDispatchWorkerStore,
    NiaTextSender,
)
from .pilot_scope import (
    PilotScopePolicyProvider,
    disabled_pilot_scope_policy,
)
from .preflight_handler import TextPreflightWorkerHandler
from .storage import ConnectorEventStore
from .worker import ConnectorWorker, ConnectorWorkerRunResult


@dataclass(frozen=True)
class ConnectorWorkerCycleResult:
    preflight: ConnectorWorkerRunResult
    nia: ConnectorWorkerRunResult
    bitrix: ConnectorWorkerRunResult


@dataclass(frozen=True)
class ConnectorWorkerComposition:
    """Tres etapas durables; el proceso llamador decide cuándo iterarlas."""

    preflight_worker: ConnectorWorker
    nia_worker: ConnectorWorker
    bitrix_worker: ConnectorWorker

    async def run_once(self) -> ConnectorWorkerCycleResult:
        return ConnectorWorkerCycleResult(
            preflight=await self.preflight_worker.run_once(),
            nia=await self.nia_worker.run_once(),
            bitrix=await self.bitrix_worker.run_once(),
        )


def compose_workers(
    store: ConnectorEventStore,
    nia_client: NiaTextSender,
    bitrix_client: BitrixMessageSender,
    *,
    worker_id: str,
    lease_seconds: int = 60,
    default_retry_after_seconds: int = 30,
    policy_provider: ExternalCallPolicyProvider = current_external_call_policy,
    pilot_policy_provider: PilotScopePolicyProvider = disabled_pilot_scope_policy,
) -> ConnectorWorkerComposition:
    """Conecta contratos inyectados sin construir Mongo, HTTP ni tareas."""

    identity = worker_id.strip()
    if not identity:
        raise ValueError("worker_id no puede estar vacío")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds debe ser positivo")
    if default_retry_after_seconds <= 0:
        raise ValueError("default_retry_after_seconds debe ser positivo")

    preflight_owner = f"{identity}:preflight"
    nia_owner = f"{identity}:nia"
    bitrix_owner = f"{identity}:bitrix"

    return ConnectorWorkerComposition(
        preflight_worker=ConnectorWorker(
            store,
            TextPreflightWorkerHandler(
                store,
                lease_owner=preflight_owner,
                policy_provider=policy_provider,
            ),
            lease_owner=preflight_owner,
            lease_seconds=lease_seconds,
        ),
        nia_worker=ConnectorWorker(
            NiaDispatchWorkerStore(store),
            NiaDispatchWorkerHandler(
                store,
                nia_client,
                lease_owner=nia_owner,
                default_retry_after_seconds=default_retry_after_seconds,
                policy_provider=policy_provider,
                pilot_policy_provider=pilot_policy_provider,
            ),
            lease_owner=nia_owner,
            lease_seconds=lease_seconds,
        ),
        bitrix_worker=ConnectorWorker(
            BitrixDispatchWorkerStore(store),
            BitrixDispatchWorkerHandler(
                store,
                bitrix_client,
                lease_owner=bitrix_owner,
                default_retry_after_seconds=default_retry_after_seconds,
                policy_provider=policy_provider,
                pilot_policy_provider=pilot_policy_provider,
            ),
            lease_owner=bitrix_owner,
            lease_seconds=lease_seconds,
        ),
    )
