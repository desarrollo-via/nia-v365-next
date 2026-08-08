"""Aprovisionamiento M86-AZ one-shot de buffers ya protegidos e inyectados."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


def _zeroize(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


class M86AZInjectedOwnedBufferProvider:
    """Doble propietario; entrega el agregado completo una sola vez."""

    __slots__ = ("_buffers", "_closed", "_used", "close_calls", "take_calls")

    def __init__(self, *, buffers: dict[str, bytearray]) -> None:
        if type(buffers) is not dict:
            raise TypeError("m86az_buffers_invalid")
        self._buffers = buffers
        self._closed = False
        self._used = False
        self.close_calls = 0
        self.take_calls = 0

    def take_all_once(self) -> dict[str, bytearray]:
        if self._closed or self._used:
            raise RuntimeError("m86az_provider_unavailable")
        self._used = True
        self.take_calls = 1
        buffers, self._buffers = self._buffers, {}
        return buffers

    def close(self) -> None:
        if not self._closed:
            _zeroize(self._buffers)
            self._closed = True
            self.close_calls = 1

    def __repr__(self) -> str:
        return "M86AZInjectedOwnedBufferProvider(<redacted>)"


class M86AZOwnedBufferProvisioningSource:
    """Valida y transfiere siete buffers sin consultar una fuente real."""

    __slots__ = ("_buffers", "_closed", "_opened", "_provider", "_used")

    def __init__(self, *, provider: M86AZInjectedOwnedBufferProvider) -> None:
        if type(provider) is not M86AZInjectedOwnedBufferProvider:
            raise TypeError("m86az_provider_invalid")
        self._provider: M86AZInjectedOwnedBufferProvider | None = provider
        self._buffers: dict[str, bytearray] = {}
        self._closed = False
        self._opened = False
        self._used = False

    def open_once(self) -> None:
        if self._used or self._closed or self._provider is None:
            raise RuntimeError("m86az_source_unavailable")
        self._used = True
        incoming: object = {}
        try:
            incoming = self._provider.take_all_once()
            if type(incoming) is not dict or tuple(incoming) != PROTECTED_SETTING_NAMES:
                raise ValueError("m86az_aggregate_invalid")
            if any(
                type(value) is not bytearray or not value or b"\x00" in value
                for value in incoming.values()
            ):
                raise ValueError("m86az_aggregate_invalid")
            self._buffers, incoming = incoming, {}
            self._opened = True
        finally:
            _zeroize(incoming)
            if not self._opened:
                self.close()

    def take_buffers_once(self) -> dict[str, bytearray]:
        if not self._opened or self._closed:
            raise RuntimeError("m86az_source_not_open")
        self._opened = False
        buffers, self._buffers = self._buffers, {}
        return buffers

    def close(self) -> None:
        _zeroize(self._buffers)
        provider, self._provider = self._provider, None
        if provider is not None:
            provider.close()
        self._opened = False
        self._closed = True

    @property
    def resources_closed(self) -> bool:
        return self._closed

    def __repr__(self) -> str:
        return "M86AZOwnedBufferProvisioningSource(<redacted>)"


@dataclass(frozen=True)
class M86AZOwnedBufferProvisioningContract:
    phase: Literal["M86-AZ"] = "M86-AZ"
    state: Literal["FIXTURE-ONLY-INERT"] = "FIXTURE-ONLY-INERT"
    provider_take_budget: Literal[1] = 1
    aggregate_name_count: Literal[7] = 7
    buffer_transfer_budget: Literal[1] = 1
    enumeration_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    same_process_required: Literal[True] = True
    owned_bytearrays_required: Literal[True] = True
    zeroize_and_close_required: Literal[True] = True
    real_provider_bound: Literal[False] = False
    real_environment_read_budget: Literal[0] = 0
    credential_manager_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


__all__ = [
    "M86AZInjectedOwnedBufferProvider",
    "M86AZOwnedBufferProvisioningContract",
    "M86AZOwnedBufferProvisioningSource",
]
