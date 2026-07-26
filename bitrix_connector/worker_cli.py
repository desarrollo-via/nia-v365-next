"""Punto de entrada del proceso separado de bitrix_connector."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import uuid
from typing import Optional, Sequence

from .worker_resources import WorkerResourceOptions
from .worker_runner import ConnectorWorkerRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecuta el worker durable separado de bitrix_connector.",
    )
    parser.add_argument("--worker-id")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--retry-after-seconds", type=int, default=30)
    parser.add_argument("--http-timeout-seconds", type=float, default=10.0)
    return parser


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def run_from_args(args: argparse.Namespace) -> int:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous_handlers: dict[signal.Signals, object] = {}

    def request_stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signal_name] = signal.getsignal(signal_name)
        signal.signal(signal_name, request_stop)

    try:
        runner = ConnectorWorkerRunner(poll_seconds=args.poll_seconds)
        result = await runner.run(
            WorkerResourceOptions(
                worker_id=args.worker_id or _default_worker_id(),
                lease_seconds=args.lease_seconds,
                default_retry_after_seconds=args.retry_after_seconds,
                http_timeout_seconds=args.http_timeout_seconds,
            ),
            stop_event=stop_event,
        )
    finally:
        for signal_name, previous in previous_handlers.items():
            signal.signal(signal_name, previous)

    print(
        json.dumps(
            {
                "status": result.status.value,
                "cycles": result.cycles,
                "reason": result.reason,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_from_args(args))


if __name__ == "__main__":
    raise SystemExit(main())
