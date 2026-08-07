"""Ensayo M86-AA de una sola transferencia previa al aprovisionamiento."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m84_windows_credential_backend import MAX_M84_BLOB_BYTES
from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


def _zeroize_buffers(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


class InjectedProtectedOriginFixture:
    """Fuente ficticia one-shot que transfiere ownership de siete buffers."""

    __slots__ = ("_buffers", "_closed", "_used", "close_calls", "transfer_calls")

    def __init__(self, *, buffers: dict[str, bytearray]) -> None:
        self._buffers = buffers
        self._used = False
        self._closed = False
        self.transfer_calls = 0
        self.close_calls = 0

    def __repr__(self) -> str:
        return "InjectedProtectedOriginFixture(<redacted>)"

    def take_buffers_once(self) -> dict[str, bytearray]:
        if self._used or self._closed:
            raise RuntimeError("m86aa_origin_fixture_unavailable")
        self._used = True
        self.transfer_calls = 1
        buffers, self._buffers = self._buffers, {}
        return buffers

    def close(self) -> None:
        if not self._closed:
            _zeroize_buffers(self._buffers)
            self._closed = True
            self.close_calls = 1


@dataclass(frozen=True)
class M86AAPreProvisioningSnapshot:
    phase: Literal["M86-AA"] = "M86-AA"
    state: Literal["READY-INERT", "NO-GO"] = "NO-GO"
    failure_category: Literal[
        "none",
        "source_contract_invalid",
        "candidate_not_fit",
        "preprovisioning_failed",
    ] = "preprovisioning_failed"
    source_transfer_calls: int = 0
    materialization_calls: int = 0
    candidate_fit_verified: bool = False
    candidate_handoff_ready_before_cleanup: bool = False
    candidate_handoff_calls: Literal[0] = 0
    source_closed: bool = False
    input_buffers_zeroized: bool = False
    candidate_blob_zeroized: bool = False
    values_exposed: Literal[False] = False
    lengths_exposed: Literal[False] = False
    real_source_bound: Literal[False] = False
    target_calls: Literal[0] = 0
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86AAPreProvisioningRehearsal:
    """Prueba fit y prepara el candidato en una sola materialización ficticia."""

    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used = False

    def run_once(
        self,
        *,
        source: InjectedProtectedOriginFixture,
    ) -> M86AAPreProvisioningSnapshot:
        if self._used or type(source) is not InjectedProtectedOriginFixture:
            self._used = True
            raise RuntimeError("m86aa_rehearsal_reuse_or_source_invalid")
        self._used = True
        buffers: object = {}
        retained_values: tuple[bytearray, ...] = ()
        blob_owner = None
        blob = bytearray()
        state: Literal["READY-INERT", "NO-GO"] = "NO-GO"
        category = "preprovisioning_failed"
        materialization_calls = 0
        fit = False
        handoff_ready = False
        candidate_zeroized = False
        try:
            buffers = source.take_buffers_once()
            if type(buffers) is dict:
                retained_values = tuple(
                    value for value in buffers.values() if type(value) is bytearray
                )
            materialization_calls = 1
            blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
            blob = blob_owner.take_blob_once()
            fit = 0 < len(blob) <= MAX_M84_BLOB_BYTES
            handoff_ready = fit
            if not fit:
                category = "candidate_not_fit"
            else:
                state = "READY-INERT"
                category = "none"
        except ValueError as error:
            reason = str(error)
            category = (
                "source_contract_invalid"
                if "allowlist_or_order" in reason or "value_invalid" in reason
                else "candidate_not_fit"
            )
        finally:
            if blob:
                blob[:] = b"\x00" * len(blob)
                candidate_zeroized = not any(blob)
            if blob_owner is not None:
                blob_owner.close()
            _zeroize_buffers(buffers)
            source.close()
        inputs_zeroized = all(not any(value) for value in retained_values)
        return M86AAPreProvisioningSnapshot(
            state=state,
            failure_category=category,
            source_transfer_calls=source.transfer_calls,
            materialization_calls=materialization_calls,
            candidate_fit_verified=fit,
            candidate_handoff_ready_before_cleanup=handoff_ready,
            source_closed=source.close_calls == 1,
            input_buffers_zeroized=inputs_zeroized,
            candidate_blob_zeroized=candidate_zeroized,
        )


__all__ = [
    "InjectedProtectedOriginFixture",
    "M86AAPreProvisioningRehearsal",
    "M86AAPreProvisioningSnapshot",
]
