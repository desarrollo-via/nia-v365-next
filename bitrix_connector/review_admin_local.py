"""Composición ejecutable, local y fixture-only del Review Admin.

Este módulo no se importa desde la aplicación principal ni desde el router.
El único punto que inicia Uvicorn es ``run_local_fixture_server``.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from fastapi import FastAPI

from .review_admin import ReviewAdminSafetyState
from .review_admin_bootstrap import OneTimeReviewAdminAuthenticator
from .review_admin_entrypoint import create_review_admin_entrypoint
from .review_admin_session import InMemoryReviewAdminSessionStore
from .review_lab_adapter import FixtureReviewLabAdapter, ReviewLabController


LOCAL_ADMIN_ORIGIN = "https://localhost:8443"
LOCAL_BIND_HOST = "127.0.0.1"
LOCAL_BIND_PORT = 8443
RUNTIME_DIRECTORY_NAME = ".review-admin-runtime"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = PROJECT_ROOT / RUNTIME_DIRECTORY_NAME
SERVER_READY_TIMEOUT_SECONDS = 20.0
SERVER_SHUTDOWN_TIMEOUT_SECONDS = 15.0


class FixtureDecisionForbidden:
    """Última barrera del ensayo: ninguna decisión debe alcanzar un adaptador."""

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def decide(self, **_: object):
        self.calls += 1
        raise RuntimeError("review_admin_fixture_decision_forbidden")

    def close(self) -> None:
        self.closed = True


def local_off_state() -> ReviewAdminSafetyState:
    return ReviewAdminSafetyState(
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        pilot_enabled=False,
        pilot_emergency_stop=True,
    )


@dataclass
class LocalReviewAdminRuntime:
    app: FastAPI
    authenticator: OneTimeReviewAdminAuthenticator
    sessions: InMemoryReviewAdminSessionStore
    decision_controller: FixtureDecisionForbidden

    async def close(self) -> None:
        await self.sessions.close()
        self.authenticator.close()
        self.decision_controller.close()


def build_local_fixture_runtime(
    *,
    bootstrap_code: str,
) -> LocalReviewAdminRuntime:
    """Compone solo memoria y fixture; no lee entorno ni abre recursos."""

    authenticator = OneTimeReviewAdminAuthenticator(
        bootstrap_code=bootstrap_code,
        actor="local-fixture-reviewer",
        credential_id="bootstrap:local-fixture:v1",
    )
    sessions = InMemoryReviewAdminSessionStore()
    decision_controller = FixtureDecisionForbidden()
    review_controller = ReviewLabController(FixtureReviewLabAdapter())
    app = create_review_admin_entrypoint(
        admin_origin=LOCAL_ADMIN_ORIGIN,
        authenticator=authenticator,
        decision_controller=decision_controller,
        review_controller=review_controller,
        safety_loader=local_off_state,
        session_store=sessions,
    )
    app.state.review_admin_local_fixture = True
    app.state.review_admin_fixture_decision_controller = decision_controller
    return LocalReviewAdminRuntime(
        app=app,
        authenticator=authenticator,
        sessions=sessions,
        decision_controller=decision_controller,
    )


def _resolve_tls_file(value: str, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_symlink():
        raise ValueError(f"review_admin_{label}_symlink_forbidden")
    try:
        candidate = raw.resolve(strict=True)
        runtime_root = RUNTIME_ROOT.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"review_admin_{label}_unavailable") from exc
    if not candidate.is_file() or candidate.suffix.lower() != ".pem":
        raise ValueError(f"review_admin_{label}_invalid")
    try:
        candidate.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError(f"review_admin_{label}_outside_runtime") from exc
    return candidate


def _resolve_control_file(value: str, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_symlink() or raw.exists():
        raise ValueError(f"review_admin_{label}_must_not_exist")
    try:
        runtime_root = RUNTIME_ROOT.resolve(strict=True)
        parent = raw.parent.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"review_admin_{label}_unavailable") from exc
    candidate = parent / raw.name
    if candidate.suffix.lower() != ".signal":
        raise ValueError(f"review_admin_{label}_invalid")
    try:
        candidate.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError(f"review_admin_{label}_outside_runtime") from exc
    return candidate


def _resolve_bootstrap_file(value: str) -> Path:
    raw = Path(value)
    if raw.is_symlink() or raw.exists():
        raise ValueError("review_admin_bootstrap_file_must_not_exist")
    try:
        runtime_root = RUNTIME_ROOT.resolve(strict=True)
        parent = raw.parent.resolve(strict=True)
    except OSError as exc:
        raise ValueError("review_admin_bootstrap_file_unavailable") from exc
    candidate = parent / raw.name
    if candidate.suffix.lower() != ".secret":
        raise ValueError("review_admin_bootstrap_file_invalid")
    try:
        candidate.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError("review_admin_bootstrap_file_outside_runtime") from exc
    return candidate


def _run_controlled_server(
    *,
    server: object,
    ready_file: Path,
    stop_file: Path,
    output: Callable[[str], None],
    ready_timeout_seconds: float = SERVER_READY_TIMEOUT_SECONDS,
    shutdown_timeout_seconds: float = SERVER_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    errors: list[BaseException] = []

    def serve() -> None:
        try:
            server.run()
        except BaseException as exc:
            errors.append(exc)

    server_thread = threading.Thread(
        target=serve,
        name="nia-review-admin-uvicorn",
        daemon=True,
    )
    server_thread.start()
    ready_deadline = time.monotonic() + ready_timeout_seconds
    while not bool(getattr(server, "started", False)):
        if errors:
            raise RuntimeError(
                "review_admin_server_failed_before_ready"
            ) from errors[0]
        if not server_thread.is_alive():
            raise RuntimeError("review_admin_server_stopped_before_ready")
        if time.monotonic() >= ready_deadline:
            setattr(server, "should_exit", True)
            server_thread.join(shutdown_timeout_seconds)
            if server_thread.is_alive():
                setattr(server, "force_exit", True)
                server_thread.join(1.0)
            raise RuntimeError("review_admin_server_ready_timeout")
        time.sleep(0.05)

    ready_file.write_text("ready\n", encoding="ascii")
    output("HTTPS LISTO · CHROME PUEDE ABRIRSE")
    while server_thread.is_alive() and not stop_file.exists():
        time.sleep(0.05)

    if not stop_file.exists():
        raise RuntimeError("review_admin_server_stopped_without_signal")
    setattr(server, "should_exit", True)
    server_thread.join(shutdown_timeout_seconds)
    if server_thread.is_alive():
        setattr(server, "force_exit", True)
        server_thread.join(1.0)
        raise RuntimeError("review_admin_server_shutdown_timeout")
    if errors:
        raise RuntimeError("review_admin_server_failed") from errors[0]


def run_local_fixture_server(
    *,
    cert_file: str,
    key_file: str,
    bootstrap_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    output: Callable[[str], None] = print,
    config_factory: Optional[Callable[..., object]] = None,
    server_factory: Optional[Callable[[object], object]] = None,
    ready_file: Optional[str] = None,
    stop_file: Optional[str] = None,
    bootstrap_file: Optional[str] = None,
) -> int:
    """Inicia el servidor solo cuando se invoca explícitamente."""

    certificate = _resolve_tls_file(cert_file, label="certificate")
    private_key = _resolve_tls_file(key_file, label="private_key")
    if (ready_file is None) != (stop_file is None):
        raise ValueError("review_admin_control_files_incomplete")
    ready_path = (
        _resolve_control_file(ready_file, label="ready_signal")
        if ready_file is not None
        else None
    )
    stop_path = (
        _resolve_control_file(stop_file, label="stop_signal")
        if stop_file is not None
        else None
    )
    bootstrap_path = (
        _resolve_bootstrap_file(bootstrap_file)
        if bootstrap_file is not None
        else None
    )
    bootstrap_code = bootstrap_factory()
    runtime = build_local_fixture_runtime(bootstrap_code=bootstrap_code)
    output("REVIEW ADMIN LOCAL · FIXTURE OFF · SIN SERVICIOS EXTERNOS")
    if bootstrap_path is None:
        output(f"BOOTSTRAP DE UN SOLO USO (5 MIN): {bootstrap_code}")
    else:
        bootstrap_path.write_text(bootstrap_code, encoding="utf-8")
        output("BOOTSTRAP DE UN SOLO USO PREPARADO PARA AUTOLOGIN")
    bootstrap_code = ""

    try:
        if config_factory is None or server_factory is None:
            import uvicorn

            config_factory = config_factory or uvicorn.Config
            server_factory = server_factory or uvicorn.Server

        config = config_factory(
            app=runtime.app,
            host=LOCAL_BIND_HOST,
            port=LOCAL_BIND_PORT,
            workers=1,
            reload=False,
            access_log=False,
            log_level="warning",
            ssl_certfile=str(certificate),
            ssl_keyfile=str(private_key),
        )
        server = server_factory(config)
        if ready_path is None or stop_path is None:
            server.run()
        else:
            _run_controlled_server(
                server=server,
                ready_file=ready_path,
                stop_file=stop_path,
                output=output,
            )
    finally:
        asyncio.run(runtime.close())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review Admin HTTPS local, fixture-only y bloqueado en off.",
    )
    parser.add_argument("--cert-file", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--ready-file", required=True)
    parser.add_argument("--stop-file", required=True)
    parser.add_argument("--bootstrap-file", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return run_local_fixture_server(
        cert_file=args.cert_file,
        key_file=args.key_file,
        ready_file=args.ready_file,
        stop_file=args.stop_file,
        bootstrap_file=args.bootstrap_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FixtureDecisionForbidden",
    "LOCAL_ADMIN_ORIGIN",
    "LOCAL_BIND_HOST",
    "LOCAL_BIND_PORT",
    "LocalReviewAdminRuntime",
    "RUNTIME_ROOT",
    "SERVER_READY_TIMEOUT_SECONDS",
    "SERVER_SHUTDOWN_TIMEOUT_SECONDS",
    "build_local_fixture_runtime",
    "build_parser",
    "local_off_state",
    "main",
    "run_local_fixture_server",
]
