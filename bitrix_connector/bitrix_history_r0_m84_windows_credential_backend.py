"""Backend M84 real-ready para un único registro genérico de Windows."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from ctypes import wintypes

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
    MAX_INJECTED_CREDENTIAL_TOTAL_BYTES,
    MAX_INJECTED_CREDENTIAL_VALUE_BYTES,
)
from .bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)


M84_BLOB_MAGIC = b"NIA-NEXT-R1-CREDENTIAL-V1\x00"
M84_BLOB_FORMAT = "ordered-name-length-value-v1"
WINDOWS_CREDENTIAL_BLOB_MAX_BYTES = 5 * 512
MAX_M84_BLOB_BYTES = WINDOWS_CREDENTIAL_BLOB_MAX_BYTES
_CRED_TYPE_GENERIC = 1


def _zeroize(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)


class WindowsGenericCredentialNativeReader(Protocol):
    async def read_generic_blob_once(self, target_id: str) -> bytearray: ...

    async def close(self) -> None: ...


class _CREDENTIALW(ctypes.Structure):
    pass


_PCREDENTIALW = ctypes.POINTER(_CREDENTIALW)


_CREDENTIALW._fields_ = (
    ("Flags", wintypes.DWORD),
    ("Type", wintypes.DWORD),
    ("TargetName", wintypes.LPWSTR),
    ("Comment", wintypes.LPWSTR),
    ("LastWritten", wintypes.FILETIME),
    ("CredentialBlobSize", wintypes.DWORD),
    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
    ("Persist", wintypes.DWORD),
    ("AttributeCount", wintypes.DWORD),
    ("Attributes", ctypes.c_void_p),
    ("TargetAlias", wintypes.LPWSTR),
    ("UserName", wintypes.LPWSTR),
)


class CtypesWindowsGenericCredentialReader:
    """Lector real perezoso: sólo CredReadW exacto y CredFree."""

    __slots__ = ("_api", "_closed", "_used")

    def __init__(self) -> None:
        self._api: object | None = None
        self._closed = False
        self._used = False

    def __repr__(self) -> str:
        return "CtypesWindowsGenericCredentialReader(<redacted>)"

    def _load_api(self) -> object:
        if self._api is not None:
            return self._api
        try:
            api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
            api.CredReadW.argtypes = (
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(_PCREDENTIALW),
            )
            api.CredReadW.restype = wintypes.BOOL
            api.CredFree.argtypes = (ctypes.c_void_p,)
            api.CredFree.restype = None
        except Exception as error:
            raise ProtectedSourceOpenFailure(
                "protected_source_api_unavailable"
            ) from error
        self._api = api
        return api

    async def read_generic_blob_once(self, target_id: str) -> bytearray:
        if (
            self._used
            or self._closed
            or target_id != M80_CREDENTIAL_TARGET_ID
        ):
            self._used = True
            raise RuntimeError("m84_native_reader_reuse_or_target_invalid")
        self._used = True
        api = self._load_api()
        pointer = _PCREDENTIALW()
        try:
            if not api.CredReadW(
                target_id,
                _CRED_TYPE_GENERIC,
                0,
                ctypes.byref(pointer),
            ):
                raise ProtectedSourceOpenFailure(
                    "protected_source_record_unavailable"
                )
            if not pointer:
                raise ProtectedSourceOpenFailure(
                    "protected_source_blob_invalid"
                )
            size = int(pointer.contents.CredentialBlobSize)
            blob_pointer = pointer.contents.CredentialBlob
            if size <= 0 or size > MAX_M84_BLOB_BYTES or not blob_pointer:
                raise ProtectedSourceOpenFailure(
                    "protected_source_blob_invalid"
                )
            native_view = (ctypes.c_ubyte * size).from_address(
                ctypes.addressof(blob_pointer.contents)
            )
            return bytearray(native_view)
        finally:
            if pointer:
                api.CredFree(pointer)

    async def close(self) -> None:
        self._api = None
        self._closed = True


def _take_u16(blob: bytearray, offset: int) -> tuple[int, int]:
    end = offset + 2
    if end > len(blob):
        raise ValueError("m84_blob_truncated")
    return int.from_bytes(blob[offset:end], "big"), end


def _take_u32(blob: bytearray, offset: int) -> tuple[int, int]:
    end = offset + 4
    if end > len(blob):
        raise ValueError("m84_blob_truncated")
    return int.from_bytes(blob[offset:end], "big"), end


def _parse_exact_blob(blob: bytearray) -> dict[str, bytearray]:
    if (
        type(blob) is not bytearray
        or len(blob) <= len(M84_BLOB_MAGIC)
        or len(blob) > MAX_M84_BLOB_BYTES
        or bytes(blob[: len(M84_BLOB_MAGIC)]) != M84_BLOB_MAGIC
    ):
        raise ValueError("m84_blob_header_invalid")
    offset = len(M84_BLOB_MAGIC)
    buffers: dict[str, bytearray] = {}
    try:
        for expected_name in PROTECTED_SETTING_NAMES:
            name_size, offset = _take_u16(blob, offset)
            if name_size <= 0 or name_size > 128:
                raise ValueError("m84_blob_name_invalid")
            name_end = offset + name_size
            if name_end > len(blob):
                raise ValueError("m84_blob_truncated")
            try:
                name = bytes(blob[offset:name_end]).decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError("m84_blob_name_invalid") from error
            offset = name_end
            if name != expected_name or name in buffers:
                raise ValueError("m84_blob_allowlist_or_order_invalid")
            value_size, offset = _take_u32(blob, offset)
            if value_size <= 0 or value_size > MAX_INJECTED_CREDENTIAL_VALUE_BYTES:
                raise ValueError("m84_blob_value_size_invalid")
            value_end = offset + value_size
            if value_end > len(blob):
                raise ValueError("m84_blob_truncated")
            value = bytearray(blob[offset:value_end])
            offset = value_end
            if b"\x00" in value:
                _zeroize(value)
                raise ValueError("m84_blob_value_invalid")
            buffers[name] = value
        if offset != len(blob) or sum(map(len, buffers.values())) > MAX_INJECTED_CREDENTIAL_TOTAL_BYTES:
            raise ValueError("m84_blob_trailing_or_total_invalid")
        return buffers
    except BaseException:
        for value in buffers.values():
            _zeroize(value)
        buffers.clear()
        raise


class WindowsCredentialManagerBackend:
    """Backend M81 one-shot sin enumeración, escritura, borrado o fallback."""

    __slots__ = ("_closed", "_native", "_used")

    def __init__(self, *, native: WindowsGenericCredentialNativeReader) -> None:
        if native is None or not callable(
            getattr(native, "read_generic_blob_once", None)
        ) or not callable(getattr(native, "close", None)):
            raise TypeError("m84_native_reader_invalid")
        allowed_methods = {"read_generic_blob_once", "close"}
        public_methods = {
            name
            for name in dir(native)
            if not name.startswith("_") and callable(getattr(native, name, None))
        }
        if public_methods != allowed_methods:
            raise TypeError("m84_native_reader_surface_rejected")
        self._native: Optional[WindowsGenericCredentialNativeReader] = native
        self._used = False
        self._closed = False

    def __repr__(self) -> str:
        return "WindowsCredentialManagerBackend(<redacted>)"

    async def fetch_exact(self, target_id: str) -> InjectedWindowsCredentialRecord:
        if (
            self._used
            or self._closed
            or self._native is None
            or target_id != M80_CREDENTIAL_TARGET_ID
        ):
            self._used = True
            raise RuntimeError("m84_backend_reuse_or_target_invalid")
        self._used = True
        blob = bytearray()
        buffers: dict[str, bytearray] = {}
        try:
            blob = await self._native.read_generic_blob_once(target_id)
            if type(blob) is not bytearray:
                raise ProtectedSourceOpenFailure(
                    "protected_source_blob_invalid"
                )
            try:
                buffers = _parse_exact_blob(blob)
            except ProtectedSourceOpenFailure:
                raise
            except (TypeError, ValueError) as error:
                raise ProtectedSourceOpenFailure(
                    "protected_source_blob_invalid"
                ) from error
            record = InjectedWindowsCredentialRecord(
                target_id=target_id,
                buffers=buffers,
            )
            buffers = {}
            return record
        finally:
            _zeroize(blob)
            for value in buffers.values():
                _zeroize(value)
            buffers.clear()

    async def close(self) -> None:
        native, self._native = self._native, None
        if native is not None and not self._closed:
            self._closed = True
            await native.close()


def build_real_windows_credential_backend() -> WindowsCredentialManagerBackend:
    """Construye el backend real sin abrir ni leer Credential Manager."""

    return WindowsCredentialManagerBackend(
        native=CtypesWindowsGenericCredentialReader()
    )


@dataclass(frozen=True)
class M84BackendContractSnapshot:
    phase: Literal["M84"] = "M84"
    state: Literal["IMPLEMENTED-NOT-READ"] = "IMPLEMENTED-NOT-READ"
    target_id: Literal["nia-next/bitrix-r1/protected-settings/v1"] = (
        M80_CREDENTIAL_TARGET_ID
    )
    blob_format: Literal["ordered-name-length-value-v1"] = M84_BLOB_FORMAT
    max_blob_bytes: Literal[2560] = WINDOWS_CREDENTIAL_BLOB_MAX_BYTES
    native_blob_limit_verified: Literal[True] = True
    exact_read_budget: Literal[1] = 1
    enumeration_budget: Literal[0] = 0
    write_budget: Literal[0] = 0
    delete_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    real_credential_reads: Literal[0] = 0
    credential_materializer_present: Literal[False] = False
    credential_record_format_verified: Literal[False] = False
    source_opened: Literal[False] = False
    command_available: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def inspect_m84_backend_contract() -> M84BackendContractSnapshot:
    return M84BackendContractSnapshot()


__all__ = [
    "CtypesWindowsGenericCredentialReader",
    "M84BackendContractSnapshot",
    "M84_BLOB_FORMAT",
    "M84_BLOB_MAGIC",
    "MAX_M84_BLOB_BYTES",
    "WINDOWS_CREDENTIAL_BLOB_MAX_BYTES",
    "WindowsCredentialManagerBackend",
    "WindowsGenericCredentialNativeReader",
    "build_real_windows_credential_backend",
    "inspect_m84_backend_contract",
]
