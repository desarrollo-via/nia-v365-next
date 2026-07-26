"""Supervisor inyectable para NIA web y el worker opcional de Bitrix.

Este módulo no contiene fábrica real de procesos ni punto de entrada ejecutable.
El adaptador de plataforma vive de forma separada en ``nia_process_launcher``.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Mapping, Optional, Protocol

from optional_bitrix_connector import is_bitrix_connector_enabled


class ProcessRole(str, Enum):
    WEB = "web"
    WORKER = "worker"


@dataclass(frozen=True)
class ProcessSpec:
    role: ProcessRole
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.command or any(not part.strip() for part in self.command):
            raise ValueError("supervisor_process_command_invalid")


@dataclass(frozen=True)
class EmbeddedSupervisorConfig:
    web_command: tuple[str, ...]
    worker_command: tuple[str, ...] = (
        "python",
        "-m",
        "bitrix_connector.worker_cli",
    )
    worker_enabled: bool = False
    max_worker_restarts: int = 2
    restart_backoff_seconds: float = 1.0
    shutdown_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        ProcessSpec(ProcessRole.WEB, self.web_command)
        ProcessSpec(ProcessRole.WORKER, self.worker_command)
        if self.max_worker_restarts < 0:
            raise ValueError("supervisor_worker_restarts_invalid")
        if self.restart_backoff_seconds <= 0:
            raise ValueError("supervisor_worker_backoff_invalid")
        if self.shutdown_timeout_seconds <= 0:
            raise ValueError("supervisor_shutdown_timeout_invalid")

    @classmethod
    def from_environ(
        cls,
        *,
        web_command: tuple[str, ...],
        environ: Optional[Mapping[str, str]] = None,
        **kwargs: object,
    ) -> "EmbeddedSupervisorConfig":
        return cls(
            web_command=web_command,
            worker_enabled=is_bitrix_connector_enabled(environ),
            **kwargs,
        )


class ManagedProcess(Protocol):
    @property
    def returncode(self) -> Optional[int]: ...

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[[ProcessSpec], Awaitable[ManagedProcess]]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class EmbeddedSupervisorResult:
    reason: str
    web_exit_code: Optional[int]
    worker_attempts: int
    worker_restarts: int
    worker_exhausted: bool
    forced_kills: int


class SupervisorStartError(RuntimeError):
    pass


class EmbeddedProcessSupervisor:
    """Mantiene NIA como proceso principal y aísla los fallos del worker."""

    def __init__(
        self,
        process_factory: ProcessFactory,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._process_factory = process_factory
        self._sleep = sleep
        self._used = False
        self._worker: Optional[ManagedProcess] = None
        self._worker_attempts = 0
        self._worker_restarts = 0
        self._worker_exhausted = False
        self._forced_kills = 0

    async def _run_worker(
        self,
        config: EmbeddedSupervisorConfig,
        stop_event: asyncio.Event,
    ) -> None:
        spec = ProcessSpec(ProcessRole.WORKER, config.worker_command)
        for attempt_index in range(config.max_worker_restarts + 1):
            if stop_event.is_set():
                return
            self._worker_attempts += 1
            try:
                self._worker = await self._process_factory(spec)
                await self._worker.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._worker = None
            else:
                self._worker = None

            if stop_event.is_set():
                return
            if attempt_index >= config.max_worker_restarts:
                self._worker_exhausted = True
                return

            self._worker_restarts += 1
            await self._sleep(
                config.restart_backoff_seconds * (2**attempt_index)
            )

    async def _stop_process(
        self,
        process: Optional[ManagedProcess],
        timeout_seconds: float,
    ) -> None:
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(
                asyncio.shield(process.wait()),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._forced_kills += 1
            process.kill()
            await process.wait()

    async def run(
        self,
        config: EmbeddedSupervisorConfig,
        *,
        stop_event: Optional[asyncio.Event] = None,
    ) -> EmbeddedSupervisorResult:
        if self._used:
            raise RuntimeError("supervisor_single_use")
        self._used = True
        stop = stop_event or asyncio.Event()

        try:
            web = await self._process_factory(
                ProcessSpec(ProcessRole.WEB, config.web_command)
            )
        except Exception as exc:
            raise SupervisorStartError("web_process_start_failed") from None

        web_wait = asyncio.create_task(web.wait())
        stop_wait = asyncio.create_task(stop.wait())
        worker_task: Optional[asyncio.Task[None]] = None
        if config.worker_enabled:
            worker_task = asyncio.create_task(self._run_worker(config, stop))

        reason = "web_exited"
        try:
            while True:
                watched: set[asyncio.Task[object]] = {
                    web_wait,  # type: ignore[arg-type]
                    stop_wait,  # type: ignore[arg-type]
                }
                if worker_task is not None:
                    watched.add(worker_task)  # type: ignore[arg-type]
                done, _ = await asyncio.wait(
                    watched,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if web_wait in done:
                    reason = "web_exited"
                    break
                if stop_wait in done:
                    reason = "stop_requested"
                    break
                if worker_task is not None and worker_task in done:
                    await worker_task
                    worker_task = None
        finally:
            stop.set()
            if worker_task is not None:
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task
            await self._stop_process(
                self._worker,
                config.shutdown_timeout_seconds,
            )
            if reason == "stop_requested":
                await self._stop_process(
                    web,
                    config.shutdown_timeout_seconds,
                )
            for task in (web_wait, stop_wait):
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return EmbeddedSupervisorResult(
            reason=reason,
            web_exit_code=web.returncode,
            worker_attempts=self._worker_attempts,
            worker_restarts=self._worker_restarts,
            worker_exhausted=self._worker_exhausted,
            forced_kills=self._forced_kills,
        )


__all__ = [
    "EmbeddedProcessSupervisor",
    "EmbeddedSupervisorConfig",
    "EmbeddedSupervisorResult",
    "ManagedProcess",
    "ProcessRole",
    "ProcessSpec",
    "SupervisorStartError",
]
