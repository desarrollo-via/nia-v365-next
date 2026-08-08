"""Compositor no invocable de referencias para el plan protegido R0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionExecutionPlan,
)
from .bitrix_history_r0_protected_session_execution_gate import (
    compose_protected_history_session_execution_gate,
)
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


Dependency = Callable[..., object]


async def fail_closed_inner_confirmation_reader() -> str:
    """Marcador seguro: nunca confirma automáticamente una sesión real."""

    raise RuntimeError("protected_history_session_inner_confirmation_required")


@dataclass(frozen=True)
class ProtectedHistorySessionPlanLauncherPreviewSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_plan_launcher_not_started"
    launcher_composed: bool = False
    path_builder_bound: bool = False
    source_builder_bound: bool = False
    resources_factory_builder_bound: bool = False
    preflight_client_builder_bound: bool = False
    reader_client_builder_bound: bool = False
    inputs_builder_bound: bool = False
    confirmation_reader_bound: bool = False
    confirmation_reader_fail_closed: bool = True
    plan_builder_bound: bool = False
    gate_composer_bound: bool = False
    path_calls: int = 0
    source_calls: int = 0
    resources_factory_calls: int = 0
    client_calls: int = 0
    inputs_calls: int = 0
    confirmation_calls: int = 0
    plan_calls: int = 0
    gate_calls: int = 0
    external_calls: int = 0


class PreparedProtectedHistorySessionPlanLauncher:
    """Retiene sólo callables públicos; no contiene inputs ni es invocable."""

    __slots__ = (
        "_confirmation_reader",
        "_gate_composer",
        "_inputs_builder",
        "_path_builder",
        "_plan_builder",
        "_preflight_client_builder",
        "_reader_client_builder",
        "_resources_factory_builder",
        "_source_builder",
    )

    def __init__(self, **dependencies: Dependency) -> None:
        for name, dependency in dependencies.items():
            setattr(self, f"_{name}", dependency)

    def __repr__(self) -> str:
        return "PreparedProtectedHistorySessionPlanLauncher(<redacted>)"


def compose_real_ready_protected_history_session_plan_launcher(
    *,
    path_builder: Dependency = Path,
    source_builder: Dependency = AllowlistedDotenvSource,
    resources_factory_builder: Dependency = PilotDiscoveryOAuthFactory,
    preflight_client_builder: Dependency = BitrixHistoryR0Client,
    reader_client_builder: Dependency = BitrixHistoryR0Client,
    inputs_builder: Dependency = BitrixHistoryR0EphemeralInputs,
    confirmation_reader: Dependency = fail_closed_inner_confirmation_reader,
    plan_builder: Dependency = ProtectedHistorySessionExecutionPlan,
    gate_composer: Dependency = compose_protected_history_session_execution_gate,
) -> PreparedProtectedHistorySessionPlanLauncher:
    """Enlaza referencias sin crear ruta, fuente, recursos, inputs, plan o gate."""

    dependencies = {
        "path_builder": path_builder,
        "source_builder": source_builder,
        "resources_factory_builder": resources_factory_builder,
        "preflight_client_builder": preflight_client_builder,
        "reader_client_builder": reader_client_builder,
        "inputs_builder": inputs_builder,
        "confirmation_reader": confirmation_reader,
        "plan_builder": plan_builder,
        "gate_composer": gate_composer,
    }
    if not all(callable(dependency) for dependency in dependencies.values()):
        raise TypeError("protected_history_session_plan_launcher_dependency_invalid")
    return PreparedProtectedHistorySessionPlanLauncher(**dependencies)


def preview_real_ready_protected_history_session_plan_launcher(
    *,
    compose_launcher: Callable[
        [], PreparedProtectedHistorySessionPlanLauncher
    ] = compose_real_ready_protected_history_session_plan_launcher,
) -> ProtectedHistorySessionPlanLauncherPreviewSnapshot:
    """Compone y descarta el launcher; nunca invoca sus referencias."""

    try:
        launcher = compose_launcher()
        if type(launcher) is not PreparedProtectedHistorySessionPlanLauncher:
            raise TypeError("protected_history_session_plan_launcher_invalid")
    except Exception:
        return ProtectedHistorySessionPlanLauncherPreviewSnapshot(
            reason="protected_history_session_plan_launcher_failed_safe"
        )
    return ProtectedHistorySessionPlanLauncherPreviewSnapshot(
        state="PREPARED",
        reason="protected_history_session_plan_launcher_prepared",
        launcher_composed=True,
        path_builder_bound=True,
        source_builder_bound=True,
        resources_factory_builder_bound=True,
        preflight_client_builder_bound=True,
        reader_client_builder_bound=True,
        inputs_builder_bound=True,
        confirmation_reader_bound=True,
        plan_builder_bound=True,
        gate_composer_bound=True,
    )


__all__ = [
    "PreparedProtectedHistorySessionPlanLauncher",
    "ProtectedHistorySessionPlanLauncherPreviewSnapshot",
    "compose_real_ready_protected_history_session_plan_launcher",
    "fail_closed_inner_confirmation_reader",
    "preview_real_ready_protected_history_session_plan_launcher",
]
