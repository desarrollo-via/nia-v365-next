"""Bucle cancelable para ejecutar el worker fuera del proceso web."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from .config import ConnectorSettings, load_settings
from .worker import ConnectorWorkerRunStatus
from .worker_resources import (
    ConnectorWorkerResourcesFactory,
    WorkerResourceOptions,
)


class WorkerRunnerStatus(str, Enum):
    INERT = "inert"
    STOPPED = "stopped"


@dataclass(frozen=True)
class WorkerRunnerResult:
    status: WorkerRunnerStatus
    cycles: int = 0
    reason: Optional[str] = None


class ConnectorWorkerRunner:
    """Termina inerte bajo bloqueo y posee el ciclo de vida de sus recursos."""

    def __init__(
        self,
        resource_factory: Optional[ConnectorWorkerResourcesFactory] = None,
        *,
        settings_provider: Callable[[], ConnectorSettings] = load_settings,
        poll_seconds: float = 1.0,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds debe ser positivo")
        self._resource_factory = resource_factory or ConnectorWorkerResourcesFactory()
        self._settings_provider = settings_provider
        self._poll_seconds = poll_seconds

    async def run(
        self,
        options: WorkerResourceOptions,
        *,
        stop_event: Optional[asyncio.Event] = None,
    ) -> WorkerRunnerResult:
        stop = stop_event or asyncio.Event()
        resources = await self._resource_factory.build(
            self._settings_provider(),
            options,
        )
        if resources is None:
            return WorkerRunnerResult(
                status=WorkerRunnerStatus.INERT,
                reason="connector_safety_barrier_active",
            )

        cycles = 0
        try:
            while not stop.is_set():
                result = await resources.composition.run_once()
                cycles += 1
                statuses = (
                    result.preflight.status,
                    result.nia.status,
                    result.bitrix.status,
                )
                if all(status is ConnectorWorkerRunStatus.IDLE for status in statuses):
                    try:
                        await asyncio.wait_for(
                            stop.wait(),
                            timeout=self._poll_seconds,
                        )
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(0)
        finally:
            await resources.close()

        return WorkerRunnerResult(
            status=WorkerRunnerStatus.STOPPED,
            cycles=cycles,
        )
