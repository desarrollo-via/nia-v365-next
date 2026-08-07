"""Binding M86-AE dormido para siete variables exactas del proceso Windows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from .bitrix_history_r0_m84_windows_credential_backend import MAX_M84_BLOB_BYTES
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


GetEnvironmentVariableW = Callable[[str, object, int], int]
WideCharToMultiByte = Callable[[int, int, object, int, object, int, object, object], int]


def _zeroize(buffer: object) -> None:
    if type(buffer) is bytearray:
        buffer[:] = b"\x00" * len(buffer)


class M86AEWindowsEnvironmentBackend:
    """Backend one-shot; las funciones WinAPI se inyectan y no se llaman al crear."""

    __slots__ = ("_closed", "_get", "_used", "_wide_to_utf8", "calls")

    def __init__(
        self,
        *,
        get_environment_variable_w: GetEnvironmentVariableW,
        wide_char_to_multi_byte: WideCharToMultiByte,
    ) -> None:
        if not callable(get_environment_variable_w) or not callable(wide_char_to_multi_byte):
            raise TypeError("m86ae_windows_api_invalid")
        self._get = get_environment_variable_w
        self._wide_to_utf8 = wide_char_to_multi_byte
        self._used: set[str] = set()
        self._closed = False
        self.calls: list[str] = []

    def take_exact_once(self, name: str) -> bytearray:
        if self._closed or name not in PROTECTED_SETTING_NAMES or name in self._used:
            raise RuntimeError("m86ae_exact_read_blocked")
        self._used.add(name)
        self.calls.append(name)
        return self._read_utf8_buffer(name)

    def _read_utf8_buffer(self, name: str) -> bytearray:
        import ctypes

        required = self._get(name, None, 0)
        if required <= 1 or required > MAX_M84_BLOB_BYTES:
            raise ValueError("m86ae_exact_value_unavailable")
        wide = ctypes.create_unicode_buffer(required)
        output = bytearray()
        try:
            written = self._get(name, wide, required)
            if written <= 0 or written >= required:
                raise ValueError("m86ae_exact_value_unavailable")
            needed = self._wide_to_utf8(65001, 0x80, wide, written, None, 0, None, None)
            if needed <= 0 or needed > MAX_M84_BLOB_BYTES:
                raise ValueError("m86ae_exact_value_unavailable")
            output = bytearray(needed)
            target = (ctypes.c_char * needed).from_buffer(output)
            converted = self._wide_to_utf8(
                65001, 0x80, wide, written, target, needed, None, None
            )
            if converted != needed or not output or b"\x00" in output:
                raise ValueError("m86ae_exact_value_unavailable")
            result, output = output, bytearray()
            return result
        finally:
            _zeroize(output)
            ctypes.memset(ctypes.addressof(wide), 0, ctypes.sizeof(wide))

    def close(self) -> None:
        self._get = None
        self._wide_to_utf8 = None
        self._closed = True

    def __repr__(self) -> str:
        return "M86AEWindowsEnvironmentBackend(<redacted>)"


class M86AEDormantWindowsEnvironmentSource:
    __slots__ = ("_backend", "_buffers", "_closed", "_opened", "_used")

    def __init__(self, *, backend: M86AEWindowsEnvironmentBackend) -> None:
        if type(backend) is not M86AEWindowsEnvironmentBackend:
            raise TypeError("m86ae_backend_invalid")
        self._backend: M86AEWindowsEnvironmentBackend | None = backend
        self._buffers: dict[str, bytearray] = {}
        self._closed = False
        self._opened = False
        self._used = False

    def open_once(self) -> None:
        if self._used or self._closed or self._backend is None:
            raise RuntimeError("m86ae_source_unavailable")
        self._used = True
        incoming: dict[str, bytearray] = {}
        try:
            for name in PROTECTED_SETTING_NAMES:
                incoming[name] = self._backend.take_exact_once(name)
            self._buffers, incoming = incoming, {}
            self._opened = True
        finally:
            for value in incoming.values():
                _zeroize(value)
            incoming.clear()
            if not self._opened:
                self.close()

    def take_buffers_once(self) -> dict[str, bytearray]:
        if not self._opened or self._closed:
            raise RuntimeError("m86ae_source_not_open")
        self._opened = False
        result, self._buffers = self._buffers, {}
        return result

    def close(self) -> None:
        for value in self._buffers.values():
            _zeroize(value)
        self._buffers.clear()
        backend, self._backend = self._backend, None
        if backend is not None:
            backend.close()
        self._opened = False
        self._closed = True

    @property
    def exact_read_calls(self) -> int:
        return 0 if self._backend is None else len(self._backend.calls)

    @property
    def resources_closed(self) -> bool:
        return self._closed


def build_m86ae_dormant_windows_environment_source() -> M86AEDormantWindowsEnvironmentSource:
    """Enlaza las dos funciones reales; no lee ninguna variable al construir."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_variable = kernel32.GetEnvironmentVariableW
    get_variable.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_variable.restype = wintypes.DWORD
    wide_to_utf8 = kernel32.WideCharToMultiByte
    wide_to_utf8.argtypes = [
        wintypes.UINT,
        wintypes.DWORD,
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.LPSTR,
        ctypes.c_int,
        wintypes.LPCSTR,
        wintypes.LPBOOL,
    ]
    wide_to_utf8.restype = ctypes.c_int
    return M86AEDormantWindowsEnvironmentSource(
        backend=M86AEWindowsEnvironmentBackend(
            get_environment_variable_w=get_variable,
            wide_char_to_multi_byte=wide_to_utf8,
        )
    )


@dataclass(frozen=True)
class M86AEDormantBindingContract:
    phase: Literal["M86-AE"] = "M86-AE"
    state: Literal["DORMANT-NO-GO"] = "DORMANT-NO-GO"
    exact_read_budget_when_authorized: Literal[7] = 7
    current_read_budget: Literal[0] = 0
    enumeration_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    real_binding_defined: Literal[True] = True
    real_factory_available: Literal[True] = True
    real_factory_invoked: Literal[False] = False
    real_binding_executed: Literal[False] = False
    immutable_value_handoff_allowed: Literal[False] = False
    target_write_budget: Literal[0] = 0
    external_calls: Literal[0] = 0


__all__ = [
    "M86AEDormantBindingContract",
    "M86AEDormantWindowsEnvironmentSource",
    "M86AEWindowsEnvironmentBackend",
    "build_m86ae_dormant_windows_environment_source",
]
