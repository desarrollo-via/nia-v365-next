"""Composición y runner propietario para el despliegue aislado G0."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Protocol

from fastapi import FastAPI

from .config import ConnectorMode, ConnectorSettings, load_settings
from .g0_entrypoint import create_g0_entrypoint
from .g0_guard import G0StopController
from .openline_r0_bridge_mount import (
    R0BridgeMountConfigurationError,
    build_optional_r0_bridge_mount,
)


G0_PUBLIC_ORIGIN_ENV = "NIA_BITRIX_G0_PUBLIC_ORIGIN"
G0_PORT_ENV = "PORT"
G0_BIND_HOST = "0.0.0.0"
G0_WORKERS = 1
G0_GRACEFUL_SHUTDOWN_SECONDS = 10.0


class G0DeploymentConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class G0DeploymentConfig:
    public_origin: str
    bind_host: str
    bind_port: int
    workers: int
    graceful_shutdown_timeout_seconds: float

    def __post_init__(self) -> None:
        if self.bind_host != G0_BIND_HOST:
            raise ValueError("g0_deployment_bind_host_invalid")
        if not 1 <= self.bind_port <= 65_535:
            raise ValueError("g0_deployment_port_invalid")
        if self.workers != G0_WORKERS:
            raise ValueError("g0_deployment_single_worker_required")
        if self.graceful_shutdown_timeout_seconds <= 0:
            raise ValueError("g0_deployment_shutdown_timeout_invalid")


class G0Server(Protocol):
    async def serve(self) -> None: ...

    def request_exit(self) -> None: ...

    def force_stop(self) -> None: ...


@dataclass(frozen=True)
class G0Deployment:
    app: FastAPI
    config: G0DeploymentConfig
    stop_controller: G0StopController
    server: G0Server


class G0RunnerStatus(str, Enum):
    SERVER_EXITED = "server_exited"
    GRACEFUL_STOP = "graceful_stop"
    FORCED_STOP = "forced_stop"


@dataclass(frozen=True)
class G0RunnerResult:
    status: G0RunnerStatus
    reason: str


class OwnerControlledUvicornServer:
    """Impide que Uvicorn sustituya las señales que posee el runner."""

    def __init__(self, config: object) -> None:
        import uvicorn

        class _Server(uvicorn.Server):
            @contextmanager
            def capture_signals(self):
                yield

        self._server = _Server(config)

    async def serve(self) -> None:
        await self._server.serve()

    def request_exit(self) -> None:
        self._server.should_exit = True

    def force_stop(self) -> None:
        self._server.should_exit = True
        self._server.force_exit = True


def _required(environ: Mapping[str, str], name: str, code: str) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise G0DeploymentConfigurationError(code)
    return value


def _deployment_inputs(
    environ: Mapping[str, str],
) -> tuple[G0DeploymentConfig, ConnectorSettings]:
    public_origin = _required(
        environ,
        G0_PUBLIC_ORIGIN_ENV,
        "g0_deployment_public_origin_missing",
    )
    raw_port = _required(
        environ,
        G0_PORT_ENV,
        "g0_deployment_port_missing",
    )
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise G0DeploymentConfigurationError(
            "g0_deployment_port_invalid"
        ) from exc
    if not 1 <= port <= 65_535:
        raise G0DeploymentConfigurationError("g0_deployment_port_invalid")

    for worker_name in ("WEB_CONCURRENCY", "NIA_BITRIX_G0_WORKERS"):
        worker_value = (environ.get(worker_name) or "").strip()
        if worker_value and worker_value != "1":
            raise G0DeploymentConfigurationError(
                "g0_deployment_single_worker_required"
            )

    settings = load_settings(environ)
    if (
        settings.requested_mode != ConnectorMode.OFF.value
        or settings.effective_mode is not ConnectorMode.OFF
        or not settings.activation_locked
        or settings.external_calls_enabled
    ):
        raise G0DeploymentConfigurationError(
            "g0_deployment_safety_state_invalid"
        )
    if (
        settings.pilot_enabled
        or not settings.pilot_emergency_stop
        or not settings.pilot_configuration_valid
    ):
        raise G0DeploymentConfigurationError(
            "g0_deployment_pilot_state_invalid"
        )
    if settings.installation_enabled or not settings.installation_configuration_valid:
        raise G0DeploymentConfigurationError(
            "g0_deployment_installation_state_invalid"
        )
    if not all(
        (
            settings.bitrix_domain,
            settings.bitrix_member_id,
            settings.bitrix_application_token,
        )
    ):
        raise G0DeploymentConfigurationError(
            "g0_deployment_bitrix_identity_missing"
        )

    config = G0DeploymentConfig(
        public_origin=public_origin,
        bind_host=G0_BIND_HOST,
        bind_port=port,
        workers=G0_WORKERS,
        graceful_shutdown_timeout_seconds=G0_GRACEFUL_SHUTDOWN_SECONDS,
    )
    return config, settings


def compose_g0_deployment(
    environ: Mapping[str, str],
    *,
    app_factory: Callable[..., FastAPI] = create_g0_entrypoint,
    config_factory: Optional[Callable[..., object]] = None,
    server_factory: Callable[[object], G0Server] = OwnerControlledUvicornServer,
) -> G0Deployment:
    """Valida todo antes de construir app, configuración ASGI o servidor."""

    config, settings = _deployment_inputs(environ)
    stop_controller = G0StopController()
    try:
        bridge_mount = build_optional_r0_bridge_mount(settings)
        app = app_factory(
            public_origin=config.public_origin,
            settings_loader=lambda: settings,
            stop_controller=stop_controller,
            receipt_observer=bridge_mount.receipt_observer,
            optional_router=bridge_mount.router,
        )
    except R0BridgeMountConfigurationError as exc:
        raise G0DeploymentConfigurationError(str(exc)) from exc
    except ValueError as exc:
        raise G0DeploymentConfigurationError(
            "g0_deployment_public_origin_invalid"
        ) from exc

    if config_factory is None:
        import uvicorn

        config_factory = uvicorn.Config
    server_config = config_factory(
        app=app,
        host=config.bind_host,
        port=config.bind_port,
        workers=config.workers,
        reload=False,
        access_log=False,
        log_level="warning",
        proxy_headers=False,
        server_header=False,
        date_header=False,
        limit_concurrency=64,
        backlog=128,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=int(
            config.graceful_shutdown_timeout_seconds
        ),
    )
    server = server_factory(server_config)
    app.state.bitrix_g0_deployment = True
    app.state.bitrix_g0_bind_host = config.bind_host
    app.state.bitrix_g0_bind_port = config.bind_port
    app.state.bitrix_g0_workers = config.workers
    app.state.bitrix_g0_r0_bridge_enabled = bridge_mount.enabled
    return G0Deployment(
        app=app,
        config=config,
        stop_controller=stop_controller,
        server=server,
    )


class G0DeploymentRunner:
    def __init__(
        self,
        *,
        signal_getter: Callable[[int], Any] = signal.getsignal,
        signal_setter: Callable[[int, Any], Any] = signal.signal,
    ) -> None:
        self._signal_getter = signal_getter
        self._signal_setter = signal_setter

    async def run(self, deployment: G0Deployment) -> G0RunnerResult:
        if deployment.config.workers != G0_WORKERS:
            raise G0DeploymentConfigurationError(
                "g0_deployment_single_worker_required"
            )
        if deployment.stop_controller.stopped:
            raise G0DeploymentConfigurationError(
                "g0_deployment_stop_already_requested"
            )

        previous_handlers: dict[int, Any] = {}
        server_task: Optional[asyncio.Task] = None
        stop_task: Optional[asyncio.Task] = None

        def request_stop(*_: object) -> None:
            deployment.stop_controller.request_stop()
            deployment.server.request_exit()

        try:
            for signal_number in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signal_number] = self._signal_getter(signal_number)
                self._signal_setter(signal_number, request_stop)

            server_task = asyncio.create_task(deployment.server.serve())
            stop_task = asyncio.create_task(deployment.stop_controller.wait())
            done, _ = await asyncio.wait(
                {server_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if (
                server_task in done
                and not deployment.stop_controller.stopped
            ):
                await self._settle(stop_task)
                server_task.result()
                deployment.stop_controller.request_stop()
                return G0RunnerResult(
                    status=G0RunnerStatus.SERVER_EXITED,
                    reason="g0_server_exited",
                )

            deployment.server.request_exit()
            try:
                await asyncio.wait_for(
                    asyncio.shield(server_task),
                    timeout=deployment.config.graceful_shutdown_timeout_seconds,
                )
            except asyncio.TimeoutError:
                deployment.server.force_stop()
                await self._settle(server_task)
                return G0RunnerResult(
                    status=G0RunnerStatus.FORCED_STOP,
                    reason="g0_shutdown_timeout",
                )
            return G0RunnerResult(
                status=G0RunnerStatus.GRACEFUL_STOP,
                reason="g0_stop_requested",
            )
        finally:
            deployment.stop_controller.request_stop()
            deployment.server.request_exit()
            await self._settle(
                *(
                    task
                    for task in (server_task, stop_task)
                    if task is not None
                )
            )
            for signal_number, previous in reversed(previous_handlers.items()):
                self._signal_setter(signal_number, previous)

    @staticmethod
    async def _settle(*tasks: asyncio.Task) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def run_from_environment(
    environ: Mapping[str, str],
) -> G0RunnerResult:
    deployment = compose_g0_deployment(environ)
    return await G0DeploymentRunner().run(deployment)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Ejecuta el ingreso G0 aislado con un único worker.",
    )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    build_parser().parse_args(argv)
    source = os.environ if environ is None else environ
    result = asyncio.run(run_from_environment(source))
    print(json.dumps({"status": result.status.value, "reason": result.reason}))
    return 1 if result.status is G0RunnerStatus.FORCED_STOP else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "G0Deployment",
    "G0DeploymentConfig",
    "G0DeploymentConfigurationError",
    "G0DeploymentRunner",
    "G0RunnerResult",
    "G0RunnerStatus",
    "OwnerControlledUvicornServer",
    "compose_g0_deployment",
]
