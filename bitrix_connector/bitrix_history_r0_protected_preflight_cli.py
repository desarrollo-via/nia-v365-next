"""Entrypoint propietario y fail-closed del preflight protegido R0."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from .bitrix_history_r0_preflight_composition import (
    BitrixHistoryClientBuilder,
    StoredOAuthResourcesFactory,
)
from .bitrix_history_r0_protected_helper import ProtectedHelperState
from .bitrix_history_r0_protected_preflight_composition import (
    ProtectedPreflightSnapshot,
    execute_protected_dotenv_preflight_once,
)


PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION = (
    "VALIDAR ENTRYPOINT PREFLIGHT R0 SOLO CON RECURSOS FICTICIOS"
)
ProtectedPreflightExecutor = Callable[..., object]


def _parse_explicit_path(argv: Sequence[str]) -> Path | None:
    values = tuple(argv)
    if (
        len(values) != 4
        or values[0] != "--confirm-code"
        or values[1] != PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION
        or values[2] != "--dotenv-path"
        or not values[3]
    ):
        return None
    try:
        return Path(values[3])
    except (TypeError, ValueError):
        return None


def _blocked(reason: str) -> ProtectedPreflightSnapshot:
    return ProtectedPreflightSnapshot(
        state=ProtectedHelperState.NO_GO,
        reason=reason,
        resources_closed=True,
    )


def _emit(snapshot: ProtectedPreflightSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    resources_factory: StoredOAuthResourcesFactory | None = None,
    client_builder: BitrixHistoryClientBuilder | None = None,
    execute_once: ProtectedPreflightExecutor = execute_protected_dotenv_preflight_once,
) -> int:
    """Posee el ciclo completo; sin dependencias inyectadas nunca abre la ruta."""

    selected_argv = tuple(sys.argv[1:] if argv is None else argv)
    dotenv_path = _parse_explicit_path(selected_argv)
    if dotenv_path is None:
        snapshot = _blocked("protected_preflight_cli_rejected")
        _emit(snapshot)
        return 2
    if resources_factory is None or client_builder is None:
        snapshot = _blocked("protected_preflight_dependencies_required")
        _emit(snapshot)
        return 2

    try:
        candidate = asyncio.run(
            execute_once(
                dotenv_path=dotenv_path,
                resources_factory=resources_factory,
                client_builder=client_builder,
            )
        )
        if type(candidate) is not ProtectedPreflightSnapshot:
            raise TypeError("protected_preflight_cli_snapshot_invalid")
        snapshot = candidate
    except KeyboardInterrupt:
        snapshot = ProtectedPreflightSnapshot(
            state=ProtectedHelperState.CANCELLED,
            reason="protected_preflight_cancelled",
            resources_closed=False,
        )
    except Exception:
        snapshot = _blocked("protected_preflight_cli_failed_safe")

    _emit(snapshot)
    if snapshot.state is ProtectedHelperState.READY:
        return 0
    if snapshot.state is ProtectedHelperState.CANCELLED:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION", "main"]
