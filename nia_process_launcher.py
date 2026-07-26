"""Adaptador Linux para el supervisor embebido de NIA y bitrix_connector.

El módulo define el punto de entrada futuro del App Service, pero importarlo no
crea procesos, no instala señales y no lee archivos de configuración.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from typing import Callable, Mapping, Optional, Sequence

from nia_process_supervisor import (
    EmbeddedProcessSupervisor,
    EmbeddedSupervisorConfig,
    EmbeddedSupervisorResult,
    ManagedProcess,
    ProcessFactory,
    ProcessSpec,
    SupervisorStartError,
)


DEFAULT_WEB_COMMAND = (
    "gunicorn",
    "-w",
    "1",
    "-k",
    "uvicorn.workers.UvicornWorker",
    "-b",
    "0.0.0.0:8000",
    "main:app",
    "--timeout",
    "600",
    "--access-logfile",
    "-",
    "--error-logfile",
    "-",
)

ResultWriter = Callable[[str], None]
SignalCleanup = Callable[[], None]
SignalInstaller = Callable[[Callable[[], None]], SignalCleanup]


async def create_managed_process(spec: ProcessSpec) -> ManagedProcess:
    """Crea un hijo sin shell y hereda stdout/stderr del contenedor."""

    return await asyncio.create_subprocess_exec(*spec.command)


def install_stop_signal_handlers(request_stop: Callable[[], None]) -> SignalCleanup:
    """Instala SIGINT/SIGTERM en el loop Linux y devuelve su limpieza."""

    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    try:
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signal_name, request_stop)
            installed.append(signal_name)
    except BaseException:
        for signal_name in installed:
            loop.remove_signal_handler(signal_name)
        raise

    def cleanup() -> None:
        for signal_name in installed:
            loop.remove_signal_handler(signal_name)

    return cleanup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Supervisa NIA web y el worker opcional de Bitrix.",
    )
    parser.add_argument("--max-worker-restarts", type=int, default=2)
    parser.add_argument("--restart-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--shutdown-timeout-seconds", type=float, default=10.0)
    return parser


def build_config(
    args: argparse.Namespace,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> EmbeddedSupervisorConfig:
    return EmbeddedSupervisorConfig.from_environ(
        web_command=DEFAULT_WEB_COMMAND,
        environ=os.environ if environ is None else environ,
        max_worker_restarts=args.max_worker_restarts,
        restart_backoff_seconds=args.restart_backoff_seconds,
        shutdown_timeout_seconds=args.shutdown_timeout_seconds,
    )


def _safe_result_payload(result: EmbeddedSupervisorResult) -> str:
    return json.dumps(
        {
            "event": "nia_process_supervisor_stopped",
            "reason": result.reason,
            "web_exit_code": result.web_exit_code,
            "worker_attempts": result.worker_attempts,
            "worker_restarts": result.worker_restarts,
            "worker_exhausted": result.worker_exhausted,
            "forced_kills": result.forced_kills,
        },
        sort_keys=True,
    )


async def run_from_args(
    args: argparse.Namespace,
    *,
    environ: Optional[Mapping[str, str]] = None,
    process_factory: ProcessFactory = create_managed_process,
    signal_installer: SignalInstaller = install_stop_signal_handlers,
    write_result: ResultWriter = print,
) -> int:
    config = build_config(args, environ=environ)
    stop_event = asyncio.Event()
    cleanup_signals = signal_installer(stop_event.set)
    try:
        result = await EmbeddedProcessSupervisor(process_factory).run(
            config,
            stop_event=stop_event,
        )
    except SupervisorStartError:
        write_result(
            json.dumps(
                {
                    "event": "nia_process_supervisor_start_failed",
                    "reason": "web_process_start_failed",
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        cleanup_signals()

    write_result(_safe_result_payload(result))
    if result.reason == "stop_requested":
        return 0
    return result.web_exit_code if result.web_exit_code is not None else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_from_args(args))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_WEB_COMMAND",
    "build_config",
    "build_parser",
    "create_managed_process",
    "install_stop_signal_handlers",
    "main",
    "run_from_args",
]
