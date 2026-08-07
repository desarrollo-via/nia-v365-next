"""Composición dormida M28 del builder protegido de sesión R0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_session_plan_materializer import (
    materialize_private_protected_history_session_plan_once,
)
from .bitrix_history_r0_protected_session_real_parser_adapter import (
    DormantProtectedSessionRealParserSnapshot,
)


Dependency = Callable[..., object]


@dataclass(frozen=True)
class DormantProtectedSessionBuilderCompositionSnapshot:
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_builder_composition_not_started"
    parser_contract_consumed: bool = False
    path_builder_bound: bool = False
    source_builder_bound: bool = False
    private_builder_bound: bool = False
    path_calls: int = 0
    source_calls: int = 0
    builder_calls: int = 0
    materializer_calls: int = 0
    parser_real_enabled: bool = False
    command_available: bool = False
    source_open_authorized: bool = False
    external_calls: int = 0
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


class PreparedDormantProtectedSessionBuilderComposition:
    """Retiene tres referencias, sin contrato, ruta, valores ni ejecución."""

    __slots__ = ("_path_builder", "_private_builder", "_source_builder")

    def __init__(
        self,
        *,
        path_builder: Dependency,
        source_builder: Dependency,
        private_builder: Dependency,
    ) -> None:
        self._path_builder = path_builder
        self._source_builder = source_builder
        self._private_builder = private_builder

    def __repr__(self) -> str:
        return "PreparedDormantProtectedSessionBuilderComposition(<redacted>)"


def compose_dormant_protected_session_builder(
    *,
    parser_contract: DormantProtectedSessionRealParserSnapshot,
    path_builder: Dependency = Path,
    source_builder: Dependency = AllowlistedDotenvSource,
    private_builder: Dependency = materialize_private_protected_history_session_plan_once,
) -> PreparedDormantProtectedSessionBuilderComposition:
    """Consume un contrato M27 ficticio y enlaza referencias sin invocarlas."""

    if (
        type(parser_contract) is not DormantProtectedSessionRealParserSnapshot
        or parser_contract.state != "PREPARED"
        or parser_contract.activation_requested is not True
        or parser_contract.exact_contract_valid is not True
        or parser_contract.authorization_calls != 1
        or parser_contract.authorization_verified is not True
        or parser_contract.parser_contract_prepared is not True
        or parser_contract.parser_real_enabled is not False
        or parser_contract.command_available is not False
        or parser_contract.builder_calls != 0
        or parser_contract.source_calls != 0
        or parser_contract.external_calls != 0
        or parser_contract.real_execution_authorized is not False
        or parser_contract.message_request_authorized is not False
        or not callable(path_builder)
        or not callable(source_builder)
        or not callable(private_builder)
    ):
        raise TypeError("protected_history_session_builder_composition_rejected")
    return PreparedDormantProtectedSessionBuilderComposition(
        path_builder=path_builder,
        source_builder=source_builder,
        private_builder=private_builder,
    )


def preview_dormant_protected_session_builder(
    *,
    parser_contract: DormantProtectedSessionRealParserSnapshot,
    compose_builder: Callable[..., object] = compose_dormant_protected_session_builder,
) -> DormantProtectedSessionBuilderCompositionSnapshot:
    """Compone el objeto dormido y publica sólo bindings y contadores cero."""

    try:
        composition = compose_builder(parser_contract=parser_contract)
        if type(composition) is not PreparedDormantProtectedSessionBuilderComposition:
            raise TypeError("protected_history_session_builder_composition_invalid")
    except BaseException:
        return DormantProtectedSessionBuilderCompositionSnapshot(
            reason="protected_history_session_builder_composition_failed_safe"
        )
    return DormantProtectedSessionBuilderCompositionSnapshot(
        state="PREPARED",
        reason="protected_history_session_builder_composition_prepared_in_doubles",
        parser_contract_consumed=True,
        path_builder_bound=True,
        source_builder_bound=True,
        private_builder_bound=True,
    )


__all__ = [
    "DormantProtectedSessionBuilderCompositionSnapshot",
    "PreparedDormantProtectedSessionBuilderComposition",
    "compose_dormant_protected_session_builder",
    "preview_dormant_protected_session_builder",
]
