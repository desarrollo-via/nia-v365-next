"""Composición M86-AD ficticia: accessor exacto a candidato M84 FIT."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m84_windows_credential_backend import MAX_M84_BLOB_BYTES
from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)
from .bitrix_history_r0_m86_injected_environment_source import (
    M86ACInjectedEnvironmentSource,
)


def _zeroize(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


@dataclass(frozen=True)
class M86ADPreProvisioningSnapshot:
    phase: Literal["M86-AD"] = "M86-AD"
    state: Literal["READY-INERT", "NO-GO"] = "NO-GO"
    failure_category: Literal[
        "none", "source_invalid", "candidate_not_fit", "composition_failed"
    ] = "composition_failed"
    source_open_calls: int = 0
    exact_name_read_calls: int = 0
    buffer_transfer_calls: int = 0
    materialization_calls: int = 0
    candidate_fit_verified: bool = False
    target_handoff_calls: Literal[0] = 0
    source_closed: bool = False
    input_buffers_zeroized: bool = False
    candidate_blob_zeroized: bool = False
    values_exposed: Literal[False] = False
    lengths_exposed: Literal[False] = False
    real_environment_bound: Literal[False] = False
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86ADInjectedEnvironmentPreProvisioningOwner:
    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used = False

    def run_once(
        self,
        *,
        source: M86ACInjectedEnvironmentSource,
    ) -> M86ADPreProvisioningSnapshot:
        if self._used or type(source) is not M86ACInjectedEnvironmentSource:
            self._used = True
            raise RuntimeError("m86ad_owner_reuse_or_source_invalid")
        self._used = True
        buffers: object = {}
        retained: tuple[bytearray, ...] = ()
        blob_owner = None
        blob = bytearray()
        state: Literal["READY-INERT", "NO-GO"] = "NO-GO"
        category = "composition_failed"
        opens = 0
        transfers = 0
        materializations = 0
        fit = False
        candidate_zeroized = False
        try:
            source.open_once()
            opens = 1
            buffers = source.take_buffers_once()
            transfers = 1
            if type(buffers) is dict:
                retained = tuple(
                    value for value in buffers.values() if type(value) is bytearray
                )
            materializations = 1
            blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
            blob = blob_owner.take_blob_once()
            fit = 0 < len(blob) <= MAX_M84_BLOB_BYTES
            if fit:
                state = "READY-INERT"
                category = "none"
            else:
                category = "candidate_not_fit"
        except ValueError as error:
            category = (
                "candidate_not_fit"
                if "blob_too_large" in str(error)
                else "source_invalid"
            )
        finally:
            if blob:
                blob[:] = b"\x00" * len(blob)
                candidate_zeroized = not any(blob)
            if blob_owner is not None:
                blob_owner.close()
            _zeroize(buffers)
            source.close()
        return M86ADPreProvisioningSnapshot(
            state=state,
            failure_category=category,
            source_open_calls=opens,
            exact_name_read_calls=source.exact_read_calls,
            buffer_transfer_calls=transfers,
            materialization_calls=materializations,
            candidate_fit_verified=fit,
            source_closed=source.resources_closed,
            input_buffers_zeroized=all(not any(value) for value in retained),
            candidate_blob_zeroized=candidate_zeroized,
        )


__all__ = [
    "M86ADInjectedEnvironmentPreProvisioningOwner",
    "M86ADPreProvisioningSnapshot",
]
