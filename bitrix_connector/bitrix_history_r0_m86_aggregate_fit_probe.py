"""Sonda M86-Y agregada para fixtures M84; no conoce fuentes reales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)


M86YFitFailureCategory = Literal[
    "none",
    "buffer_contract_invalid",
    "buffer_value_invalid",
    "native_blob_limit_exceeded",
    "fit_probe_failed",
]


def _zeroize_owned(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


@dataclass(frozen=True)
class M86YAggregateFitSnapshot:
    phase: Literal["M86-Y"] = "M86-Y"
    state: Literal["FIT", "NO-GO"] = "NO-GO"
    failure_category: M86YFitFailureCategory = "fit_probe_failed"
    probe_calls: Literal[1] = 1
    required_buffer_set_present: bool = False
    fits_native_blob_limit: bool = False
    input_buffers_zeroized: bool = False
    candidate_blob_zeroized: bool = False
    values_exposed: Literal[False] = False
    individual_lengths_exposed: Literal[False] = False
    aggregate_length_exposed: Literal[False] = False
    real_source_bound: Literal[False] = False
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86YAggregateFitProbe:
    """Consume y limpia una única colección de buffers ya inyectados."""

    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used = False

    def probe_once(self, *, buffers: dict[str, bytearray]) -> M86YAggregateFitSnapshot:
        if self._used:
            raise RuntimeError("m86y_fit_probe_reused")
        self._used = True
        blob_owner = None
        blob = bytearray()
        state: Literal["FIT", "NO-GO"] = "NO-GO"
        category: M86YFitFailureCategory = "fit_probe_failed"
        required_present = False
        fits = False
        candidate_zeroized = False
        try:
            blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
            required_present = True
            blob = blob_owner.take_blob_once()
            fits = True
            state = "FIT"
            category = "none"
        except ValueError as error:
            reason = str(error)
            if "allowlist_or_order" in reason:
                category = "buffer_contract_invalid"
            elif "blob_too_large" in reason:
                required_present = True
                category = "native_blob_limit_exceeded"
            elif "value_invalid" in reason or "total_invalid" in reason:
                required_present = True
                category = "buffer_value_invalid"
        finally:
            if blob:
                blob[:] = b"\x00" * len(blob)
                candidate_zeroized = not any(blob)
            if blob_owner is not None:
                blob_owner.close()
            _zeroize_owned(buffers)
        return M86YAggregateFitSnapshot(
            state=state,
            failure_category=category,
            required_buffer_set_present=required_present,
            fits_native_blob_limit=fits,
            input_buffers_zeroized=type(buffers) is dict and not buffers,
            candidate_blob_zeroized=candidate_zeroized,
        )


__all__ = [
    "M86YAggregateFitProbe",
    "M86YAggregateFitSnapshot",
    "M86YFitFailureCategory",
]
