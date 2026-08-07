"""Adaptador M86-AC allowlisted sobre un accessor ficticio de buffers."""

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


class InjectedExactEnvironmentAccessor:
    """Doble que entrega cada nombre exacto una vez, sin enumeración."""

    __slots__ = ("_buffers", "_closed", "calls", "close_calls")

    def __init__(self, *, buffers: dict[str, bytearray]) -> None:
        self._buffers = buffers
        self._closed = False
        self.calls: list[str] = []
        self.close_calls = 0

    def take_exact_once(self, name: str) -> bytearray:
        if self._closed or name not in PROTECTED_SETTING_NAMES or name in self.calls:
            raise RuntimeError("m86ac_accessor_read_blocked")
        self.calls.append(name)
        return self._buffers.pop(name, bytearray())

    def close(self) -> None:
        if not self._closed:
            _zeroize(self._buffers)
            self._closed = True
            self.close_calls = 1

    def __repr__(self) -> str:
        return "InjectedExactEnvironmentAccessor(<redacted>)"


class M86ACInjectedEnvironmentSource:
    """Agrupa siete buffers exactos; no conoce el entorno real del proceso."""

    __slots__ = (
        "_accessor",
        "_buffers",
        "_closed",
        "_exact_read_calls",
        "_opened",
        "_used",
    )

    def __init__(self, *, accessor: InjectedExactEnvironmentAccessor) -> None:
        if type(accessor) is not InjectedExactEnvironmentAccessor:
            raise TypeError("m86ac_accessor_invalid")
        self._accessor: InjectedExactEnvironmentAccessor | None = accessor
        self._buffers: dict[str, bytearray] = {}
        self._opened = False
        self._closed = False
        self._exact_read_calls = 0
        self._used = False

    def open_once(self) -> None:
        if self._used or self._closed or self._accessor is None:
            raise RuntimeError("m86ac_source_unavailable")
        self._used = True
        incoming: dict[str, bytearray] = {}
        try:
            for name in PROTECTED_SETTING_NAMES:
                value = self._accessor.take_exact_once(name)
                self._exact_read_calls += 1
                if type(value) is not bytearray or not value or b"\x00" in value:
                    if type(value) is bytearray:
                        value[:] = b"\x00" * len(value)
                    raise ValueError("m86ac_exact_buffer_invalid")
                incoming[name] = value
            self._buffers = incoming
            incoming = {}
            self._opened = True
        finally:
            _zeroize(incoming)
            if not self._opened:
                self.close()

    def take_buffers_once(self) -> dict[str, bytearray]:
        if not self._opened or self._closed:
            raise RuntimeError("m86ac_source_not_open")
        self._opened = False
        buffers, self._buffers = self._buffers, {}
        return buffers

    def close(self) -> None:
        _zeroize(self._buffers)
        accessor, self._accessor = self._accessor, None
        if accessor is not None:
            accessor.close()
        self._opened = False
        self._closed = True

    @property
    def exact_read_calls(self) -> int:
        return self._exact_read_calls

    @property
    def resources_closed(self) -> bool:
        return self._closed

    def __repr__(self) -> str:
        return "M86ACInjectedEnvironmentSource(<redacted>)"


@dataclass(frozen=True)
class M86ACInjectedEnvironmentContract:
    phase: Literal["M86-AC"] = "M86-AC"
    state: Literal["FIXTURE-ONLY"] = "FIXTURE-ONLY"
    exact_read_budget: Literal[7] = 7
    enumeration_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    real_environment_binding_present: Literal[False] = False
    immutable_string_handoff_allowed: Literal[False] = False
    owned_bytearray_handoff_required: Literal[True] = True
    close_and_zeroize_required: Literal[True] = True
    values_read: Literal[False] = False
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0


__all__ = [
    "InjectedExactEnvironmentAccessor",
    "M86ACInjectedEnvironmentContract",
    "M86ACInjectedEnvironmentSource",
]
