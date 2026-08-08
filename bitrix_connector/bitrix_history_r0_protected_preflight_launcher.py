"""Launcher real-ready del preflight protegido; su CLI sólo prepara."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_preflight_composition import (
    BitrixHistoryClientBuilder,
    StoredOAuthResourcesFactory,
)
from .bitrix_history_r0_protected_preflight_cli import main as owner_entrypoint
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


PROTECTED_PREFLIGHT_LAUNCHER_CONFIRMATION = (
    "PREPARAR LAUNCHER PREFLIGHT R0 SIN EJECUTAR"
)
OwnerEntrypoint = Callable[..., int]
ResourcesFactoryBuilder = Callable[[], StoredOAuthResourcesFactory]


@dataclass(frozen=True)
class ProtectedLauncherPreviewSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "protected_preflight_launcher_not_started"
    launcher_composed: bool = False
    owner_entrypoint_bound: bool = False
    resources_factory_bound: bool = False
    client_builder_bound: bool = False
    source_open_calls: int = 0
    preflight_calls: int = 0
    external_calls: int = 0


class PreparedProtectedPreflightLauncher:
    """Closure redactada; sólo una autorización futura podrá invocarla."""

    __slots__ = ("_client_builder", "_owner", "_resources_factory")

    def __init__(
        self,
        *,
        owner: OwnerEntrypoint,
        resources_factory: StoredOAuthResourcesFactory,
        client_builder: BitrixHistoryClientBuilder,
    ) -> None:
        self._owner = owner
        self._resources_factory = resources_factory
        self._client_builder = client_builder

    def __call__(self, argv: Sequence[str]) -> int:
        return self._owner(
            argv,
            resources_factory=self._resources_factory,
            client_builder=self._client_builder,
        )

    def __repr__(self) -> str:
        return "PreparedProtectedPreflightLauncher(<redacted>)"


def compose_real_ready_launcher(
    *,
    resources_factory_builder: ResourcesFactoryBuilder = PilotDiscoveryOAuthFactory,
    client_builder: BitrixHistoryClientBuilder = BitrixHistoryR0Client,
    owner: OwnerEntrypoint = owner_entrypoint,
) -> PreparedProtectedPreflightLauncher:
    """Enlaza tipos existentes; no abre fuente ni construye clientes HTTP."""

    resources_factory = resources_factory_builder()
    if not callable(getattr(resources_factory, "build", None)):
        raise TypeError("protected_preflight_resources_factory_invalid")
    if not callable(client_builder) or not callable(owner):
        raise TypeError("protected_preflight_launcher_dependency_invalid")
    return PreparedProtectedPreflightLauncher(
        owner=owner,
        resources_factory=resources_factory,
        client_builder=client_builder,
    )


def _parse_preview(argv: Sequence[str]) -> Path | None:
    values = tuple(argv)
    if (
        len(values) != 4
        or values[0] != "--confirm-code"
        or values[1] != PROTECTED_PREFLIGHT_LAUNCHER_CONFIRMATION
        or values[2] != "--dotenv-path"
        or not values[3]
    ):
        return None
    try:
        return Path(values[3])
    except (TypeError, ValueError):
        return None


def _emit(snapshot: ProtectedLauncherPreviewSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    compose_launcher: Callable[[], PreparedProtectedPreflightLauncher] = (
        compose_real_ready_launcher
    ),
) -> int:
    """Compone y descarta el launcher; nunca lo invoca ni abre la ruta."""

    selected_argv = tuple(sys.argv[1:] if argv is None else argv)
    if _parse_preview(selected_argv) is None:
        snapshot = ProtectedLauncherPreviewSnapshot(
            reason="protected_preflight_launcher_rejected"
        )
        _emit(snapshot)
        return 2

    try:
        launcher = compose_launcher()
        if type(launcher) is not PreparedProtectedPreflightLauncher:
            raise TypeError("protected_preflight_launcher_invalid")
        snapshot = ProtectedLauncherPreviewSnapshot(
            state="PREPARED",
            reason="protected_preflight_launcher_prepared",
            launcher_composed=True,
            owner_entrypoint_bound=True,
            resources_factory_bound=True,
            client_builder_bound=True,
        )
    except Exception:
        snapshot = ProtectedLauncherPreviewSnapshot(
            reason="protected_preflight_launcher_failed_safe"
        )

    _emit(snapshot)
    return 0 if snapshot.state == "PREPARED" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PROTECTED_PREFLIGHT_LAUNCHER_CONFIRMATION",
    "PreparedProtectedPreflightLauncher",
    "ProtectedLauncherPreviewSnapshot",
    "compose_real_ready_launcher",
    "main",
]
