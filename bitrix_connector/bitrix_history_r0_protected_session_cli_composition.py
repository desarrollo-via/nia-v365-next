"""Composición M25 real-ready, redactada y no invocable del owner R0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_session_cli import (
    execute_fixture_protected_session_owner_once,
)
from .bitrix_history_r0_protected_session_gate_owner import (
    execute_materialized_history_session_gate_once,
)
from .bitrix_history_r0_protected_session_plan_launcher import (
    compose_real_ready_protected_history_session_plan_launcher,
    fail_closed_inner_confirmation_reader,
)
from .bitrix_history_r0_protected_session_plan_materializer import (
    materialize_private_protected_history_session_plan_once,
)


Dependency = Callable[..., object]
PROTECTED_SESSION_REAL_SOURCE_NAME = "local-dotenv"


async def fail_closed_outer_confirmation_reader() -> str:
    """Marcador real-ready que nunca autoriza automáticamente al owner."""

    raise RuntimeError("protected_history_session_outer_confirmation_required")


@dataclass(frozen=True)
class ProtectedHistorySessionOwnerCompositionPreviewSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_owner_composition_not_started"
    source_name_bound: bool = False
    path_builder_bound: bool = False
    source_builder_bound: bool = False
    plan_launcher_bound: bool = False
    materializer_bound: bool = False
    inner_confirmation_bound: bool = False
    outer_confirmation_bound: bool = False
    gate_owner_bound: bool = False
    cli_owner_bound: bool = False
    real_parser_blocked: bool = True
    command_available: bool = False
    source_select_calls: int = 0
    path_calls: int = 0
    source_calls: int = 0
    plan_launcher_calls: int = 0
    materializer_calls: int = 0
    inner_confirmation_calls: int = 0
    outer_confirmation_calls: int = 0
    gate_owner_calls: int = 0
    cli_owner_calls: int = 0
    external_calls: int = 0


class PreparedProtectedHistorySessionOwnerComposition:
    """Retiene referencias sin valores, ruta concreta ni método de ejecución."""

    __slots__ = (
        "_cli_owner",
        "_gate_owner",
        "_inner_confirmation_reader",
        "_materializer",
        "_outer_confirmation_reader",
        "_path_builder",
        "_plan_launcher",
        "_source_builder",
        "_source_name",
    )

    def __init__(self, *, source_name: str, **dependencies: Dependency) -> None:
        self._source_name = source_name
        for name, dependency in dependencies.items():
            setattr(self, f"_{name}", dependency)

    def __repr__(self) -> str:
        return "PreparedProtectedHistorySessionOwnerComposition(<redacted>)"


def compose_real_ready_protected_session_owner(
    *,
    source_name: str = PROTECTED_SESSION_REAL_SOURCE_NAME,
    path_builder: Dependency = Path,
    source_builder: Dependency = AllowlistedDotenvSource,
    plan_launcher: Dependency = compose_real_ready_protected_history_session_plan_launcher,
    materializer: Dependency = materialize_private_protected_history_session_plan_once,
    inner_confirmation_reader: Dependency = fail_closed_inner_confirmation_reader,
    outer_confirmation_reader: Dependency = fail_closed_outer_confirmation_reader,
    gate_owner: Dependency = execute_materialized_history_session_gate_once,
    cli_owner: Dependency = execute_fixture_protected_session_owner_once,
) -> PreparedProtectedHistorySessionOwnerComposition:
    """Enlaza referencias; no selecciona fuente ni crea ruta, plan u owner."""

    dependencies = {
        "path_builder": path_builder,
        "source_builder": source_builder,
        "plan_launcher": plan_launcher,
        "materializer": materializer,
        "inner_confirmation_reader": inner_confirmation_reader,
        "outer_confirmation_reader": outer_confirmation_reader,
        "gate_owner": gate_owner,
        "cli_owner": cli_owner,
    }
    if source_name != PROTECTED_SESSION_REAL_SOURCE_NAME or not all(
        callable(dependency) for dependency in dependencies.values()
    ):
        raise TypeError("protected_history_session_owner_composition_dependency_invalid")
    return PreparedProtectedHistorySessionOwnerComposition(
        source_name=source_name,
        **dependencies,
    )


def preview_real_ready_protected_session_owner(
    *,
    compose_owner: Callable[
        [], PreparedProtectedHistorySessionOwnerComposition
    ] = compose_real_ready_protected_session_owner,
) -> ProtectedHistorySessionOwnerCompositionPreviewSnapshot:
    """Compone y descarta el owner; nunca invoca ninguna referencia."""

    try:
        owner = compose_owner()
        if type(owner) is not PreparedProtectedHistorySessionOwnerComposition:
            raise TypeError("protected_history_session_owner_composition_invalid")
    except Exception:
        return ProtectedHistorySessionOwnerCompositionPreviewSnapshot(
            reason="protected_history_session_owner_composition_failed_safe"
        )
    return ProtectedHistorySessionOwnerCompositionPreviewSnapshot(
        state="PREPARED",
        reason="protected_history_session_owner_composition_prepared",
        source_name_bound=True,
        path_builder_bound=True,
        source_builder_bound=True,
        plan_launcher_bound=True,
        materializer_bound=True,
        inner_confirmation_bound=True,
        outer_confirmation_bound=True,
        gate_owner_bound=True,
        cli_owner_bound=True,
    )


__all__ = [
    "PROTECTED_SESSION_REAL_SOURCE_NAME",
    "PreparedProtectedHistorySessionOwnerComposition",
    "ProtectedHistorySessionOwnerCompositionPreviewSnapshot",
    "compose_real_ready_protected_session_owner",
    "fail_closed_outer_confirmation_reader",
    "preview_real_ready_protected_session_owner",
]
