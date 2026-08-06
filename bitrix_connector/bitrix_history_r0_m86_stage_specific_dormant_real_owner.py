"""Owner M86-AT real-ready, dormido y sin superficie de ejecución."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    build_m86ae_dormant_windows_environment_source,
)


RealSourceFactory = Callable[[], M86AEDormantWindowsEnvironmentSource]


@dataclass(frozen=True)
class M86ATDormantRealPreview:
    phase: Literal["M86-AT"] = "M86-AT"
    state: Literal["DORMANT-WAITING-AUTHORIZATION-DESIGN"] = (
        "DORMANT-WAITING-AUTHORIZATION-DESIGN"
    )
    real_factory_bound: Literal[True] = True
    real_factory_called: Literal[False] = False
    stage_specific_categories_reused: Literal[True] = True
    authorization_literal_prepared: Literal[False] = False
    authorization_received: Literal[False] = False
    execution_surface_available: Literal[False] = False
    execution_surface_has_cli: Literal[False] = False
    current_real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0


class M86ATStageSpecificDormantRealOwner:
    __slots__ = ("_source_factory",)

    def __init__(
        self,
        *,
        source_factory: RealSourceFactory = build_m86ae_dormant_windows_environment_source,
    ) -> None:
        if not callable(source_factory):
            raise TypeError("m86at_source_factory_invalid")
        self._source_factory = source_factory

    def preview(self) -> M86ATDormantRealPreview:
        return M86ATDormantRealPreview()


__all__ = [
    "M86ATDormantRealPreview",
    "M86ATStageSpecificDormantRealOwner",
]
