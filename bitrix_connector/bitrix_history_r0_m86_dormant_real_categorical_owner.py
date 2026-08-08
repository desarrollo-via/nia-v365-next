"""Owner M86-AN real-ready, dormido y sin CLI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m84_windows_credential_backend import MAX_M84_BLOB_BYTES
from .bitrix_history_r0_m86_categorical_probe_authorization import (
    M86AOAuthorizationContract,
)
from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)
from .bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    build_m86ae_dormant_windows_environment_source,
)
from .bitrix_history_r0_m86_public_aggregate_diagnostic import (
    M86ALPublicAggregateDiagnostic,
    build_m86al_public_diagnostic,
)


SourceFactory = Callable[[], M86AEDormantWindowsEnvironmentSource]


def _zeroize_buffers(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


@dataclass(frozen=True)
class M86ANDormantPreview:
    phase: Literal["M86-AN"] = "M86-AN"
    state: Literal["DORMANT-WAITING-AUTHORIZATION"] = "DORMANT-WAITING-AUTHORIZATION"
    real_factory_bound: Literal[True] = True
    real_factory_called: Literal[False] = False
    execution_surface_has_cli: Literal[False] = False
    current_real_read_budget: Literal[0] = 0
    authorization_received: Literal[False] = False
    external_calls: Literal[0] = 0


class M86ANDormantRealCategoricalOwner:
    __slots__ = ("_source_factory", "_used")

    def __init__(
        self,
        *,
        source_factory: SourceFactory = build_m86ae_dormant_windows_environment_source,
    ) -> None:
        if not callable(source_factory):
            raise TypeError("m86an_source_factory_invalid")
        self._source_factory = source_factory
        self._used = False

    def preview(self) -> M86ANDormantPreview:
        return M86ANDormantPreview()

    def run_once(self, *, confirm_code: str) -> M86ALPublicAggregateDiagnostic:
        if self._used:
            raise RuntimeError("m86an_owner_already_used")
        self._used = True
        if not M86AOAuthorizationContract().accepts(confirm_code):
            return build_m86al_public_diagnostic("authorization_invalid")

        source = None
        buffers: object = {}
        blob_owner = None
        blob = bytearray()
        category = "composition_failed"
        cleanup_ok = True
        try:
            try:
                source = self._source_factory()
                if type(source) is not M86AEDormantWindowsEnvironmentSource:
                    raise TypeError("m86an_source_invalid")
                source.open_once()
                buffers = source.take_buffers_once()
            except BaseException:
                category = "source_aggregate_unavailable"
            else:
                try:
                    blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
                    blob = blob_owner.take_blob_once()
                    category = "none" if 0 < len(blob) <= MAX_M84_BLOB_BYTES else "candidate_not_fit"
                except ValueError:
                    category = "candidate_not_fit"
                except BaseException:
                    category = "composition_failed"
        finally:
            if blob:
                blob[:] = b"\x00" * len(blob)
            try:
                if blob_owner is not None:
                    blob_owner.close()
            except BaseException:
                cleanup_ok = False
            _zeroize_buffers(buffers)
            try:
                if source is not None:
                    source.close()
            except BaseException:
                cleanup_ok = False
        if not cleanup_ok:
            category = "cleanup_ambiguous"
        return build_m86al_public_diagnostic(category)


__all__ = [
    "M86ANDormantPreview",
    "M86ANDormantRealCategoricalOwner",
]
