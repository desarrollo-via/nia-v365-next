"""Composición M47 preparada, redactada y no invocable del diagnóstico existente."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_existing_diagnostic_owner import (
    execute_existing_history_diagnostic_once,
)
from .bitrix_history_r0_preflight_composition import (
    execute_stored_oauth_history_preflight_once,
)
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


Dependency = Callable[..., object]


@dataclass(frozen=True)
class ExistingHistoryDiagnosticCompositionPreviewSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "bitrix_history_existing_composition_not_started"
    diagnostic_owner_bound: bool = False
    protected_preflight_bound: bool = False
    protected_resources_factory_bound: bool = False
    history_client_builder_bound: bool = False
    dialog_read_budget: int = 1
    history_read_budget: int = 1
    diagnostic_owner_calls: int = 0
    preflight_calls: int = 0
    resources_factory_calls: int = 0
    history_client_builder_calls: int = 0
    dialog_read_calls: int = 0
    history_read_calls: int = 0
    wait_calls: int = 0
    message_requests: int = 0
    mutation_calls: int = 0
    oauth_refresh_calls: int = 0
    external_calls: int = 0
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    source_open_authorized: bool = False
    real_execution_authorized: bool = False
    command_available: bool = False


class PreparedExistingHistoryDiagnosticComposition:
    """Retiene sólo referencias; no contiene valores ni método de ejecución."""

    __slots__ = (
        "_diagnostic_owner",
        "_history_client_builder",
        "_protected_preflight",
        "_protected_resources_factory",
    )

    def __init__(self, **dependencies: Dependency) -> None:
        for name, dependency in dependencies.items():
            setattr(self, f"_{name}", dependency)

    def __repr__(self) -> str:
        return "PreparedExistingHistoryDiagnosticComposition(<redacted>)"


def compose_existing_history_diagnostic_preview(
    *,
    diagnostic_owner: Dependency = execute_existing_history_diagnostic_once,
    protected_preflight: Dependency = execute_stored_oauth_history_preflight_once,
    protected_resources_factory: Dependency = PilotDiscoveryOAuthFactory,
    history_client_builder: Dependency = BitrixHistoryR0Client,
) -> PreparedExistingHistoryDiagnosticComposition:
    """Enlaza contratos futuros sin construir recursos ni invocar dependencias."""

    dependencies = {
        "diagnostic_owner": diagnostic_owner,
        "protected_preflight": protected_preflight,
        "protected_resources_factory": protected_resources_factory,
        "history_client_builder": history_client_builder,
    }
    if not all(callable(dependency) for dependency in dependencies.values()):
        raise TypeError("bitrix_history_existing_composition_dependency_invalid")
    return PreparedExistingHistoryDiagnosticComposition(**dependencies)


def preview_existing_history_diagnostic_composition(
    *,
    compose_owner: Callable[
        [], PreparedExistingHistoryDiagnosticComposition
    ] = compose_existing_history_diagnostic_preview,
) -> ExistingHistoryDiagnosticCompositionPreviewSnapshot:
    """Compone y descarta referencias; nunca habilita ni ejecuta el diagnóstico."""

    try:
        composition = compose_owner()
        if type(composition) is not PreparedExistingHistoryDiagnosticComposition:
            raise TypeError("bitrix_history_existing_composition_invalid")
    except Exception:
        return ExistingHistoryDiagnosticCompositionPreviewSnapshot(
            reason="bitrix_history_existing_composition_failed_safe"
        )
    return ExistingHistoryDiagnosticCompositionPreviewSnapshot(
        state="PREPARED",
        reason="bitrix_history_existing_composition_prepared",
        diagnostic_owner_bound=True,
        protected_preflight_bound=True,
        protected_resources_factory_bound=True,
        history_client_builder_bound=True,
    )


__all__ = [
    "ExistingHistoryDiagnosticCompositionPreviewSnapshot",
    "PreparedExistingHistoryDiagnosticComposition",
    "compose_existing_history_diagnostic_preview",
    "preview_existing_history_diagnostic_composition",
]
