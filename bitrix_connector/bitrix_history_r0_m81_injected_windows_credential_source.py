"""Fuente M81 compatible con Credential Manager sólo mediante backend inyectado."""

from __future__ import annotations

from typing import Protocol

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperSnapshot,
    ProtectedOperation,
    ProtectedSourceOpenFailure,
    execute_protected_helper_once,
)


MAX_INJECTED_CREDENTIAL_VALUE_BYTES = 8 * 1024
MAX_INJECTED_CREDENTIAL_TOTAL_BYTES = 32 * 1024


def _zeroize(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


class InjectedWindowsCredentialRecord:
    """Entrega una sola vez buffers propios; nunca representa su contenido."""

    __slots__ = ("_buffers", "_target_id", "_used")

    def __init__(self, *, target_id: str, buffers: dict[str, bytearray]) -> None:
        self._target_id = target_id
        self._buffers = buffers
        self._used = False

    @property
    def target_id(self) -> str:
        return self._target_id

    def take_buffers_once(self) -> dict[str, bytearray]:
        if self._used:
            raise RuntimeError("m81_credential_record_reused")
        self._used = True
        buffers, self._buffers = self._buffers, {}
        return buffers

    def clear(self) -> None:
        _zeroize(self._buffers)
        self._used = True

    def __repr__(self) -> str:
        return "InjectedWindowsCredentialRecord(<redacted>)"


class InjectedWindowsCredentialBackend(Protocol):
    """Backend mínimo: un target exacto, sin método de enumeración o escritura."""

    async def fetch_exact(
        self, target_id: str
    ) -> InjectedWindowsCredentialRecord: ...

    async def close(self) -> None: ...


class WindowsCredentialProtectedValueSource:
    """Implementa ProtectedValueSource sin conocer ninguna API o almacén real."""

    __slots__ = ("_backend", "_backend_closed", "_buffers", "_opened", "_used")

    def __init__(self, *, backend: InjectedWindowsCredentialBackend) -> None:
        if backend is None or not callable(getattr(backend, "fetch_exact", None)):
            raise TypeError("m81_credential_backend_invalid")
        if not callable(getattr(backend, "close", None)):
            raise TypeError("m81_credential_backend_invalid")
        self._backend: InjectedWindowsCredentialBackend | None = backend
        self._backend_closed = False
        self._buffers: dict[str, bytearray] = {}
        self._opened = False
        self._used = False

    async def _close_backend_once(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None and not self._backend_closed:
            self._backend_closed = True
            await backend.close()

    @staticmethod
    def _validate_buffers(buffers: object) -> dict[str, bytearray]:
        if type(buffers) is not dict or set(buffers) != set(PROTECTED_SETTING_NAMES):
            raise ValueError("m81_credential_allowlist_invalid")
        total = 0
        for name in PROTECTED_SETTING_NAMES:
            value = buffers[name]
            if (
                type(value) is not bytearray
                or not value
                or len(value) > MAX_INJECTED_CREDENTIAL_VALUE_BYTES
                or b"\x00" in value
            ):
                raise ValueError("m81_credential_value_invalid")
            total += len(value)
        if total > MAX_INJECTED_CREDENTIAL_TOTAL_BYTES:
            raise ValueError("m81_credential_record_too_large")
        return buffers

    async def open(self) -> None:
        if self._used:
            raise RuntimeError("m81_credential_source_reused")
        self._used = True
        incoming: object = {}
        record: InjectedWindowsCredentialRecord | None = None
        try:
            backend = self._backend
            if backend is None:
                raise RuntimeError("m81_credential_backend_unavailable")
            record = await backend.fetch_exact(M80_CREDENTIAL_TARGET_ID)
            try:
                if type(record) is not InjectedWindowsCredentialRecord:
                    raise TypeError("m81_credential_record_invalid")
                incoming = record.take_buffers_once()
                if record.target_id != M80_CREDENTIAL_TARGET_ID:
                    raise ValueError("m81_credential_target_mismatch")
                self._buffers = self._validate_buffers(incoming)
            except ProtectedSourceOpenFailure:
                raise
            except (RuntimeError, TypeError, ValueError) as error:
                raise ProtectedSourceOpenFailure(
                    "protected_source_contract_invalid"
                ) from error
            incoming = {}
            self._opened = True
        except BaseException:
            _zeroize(incoming)
            if type(record) is InjectedWindowsCredentialRecord:
                record.clear()
            try:
                await self._close_backend_once()
            except BaseException as close_error:
                raise RuntimeError("m81_credential_backend_close_failed") from close_error
            raise

    async def read(self, name: str) -> bytearray:
        if not self._opened or name not in PROTECTED_SETTING_NAMES:
            raise RuntimeError("m81_credential_read_blocked")
        return self._buffers.pop(name, bytearray())

    async def close(self) -> None:
        _zeroize(self._buffers)
        self._opened = False
        await self._close_backend_once()

    def __repr__(self) -> str:
        return "WindowsCredentialProtectedValueSource(<redacted>)"


async def execute_injected_windows_credential_helper_once(
    *,
    backend: InjectedWindowsCredentialBackend,
    operation: ProtectedOperation,
) -> ProtectedHelperSnapshot:
    """Compone la fuente inyectada con el helper existente una sola vez."""

    source = WindowsCredentialProtectedValueSource(backend=backend)
    return await execute_protected_helper_once(source=source, operation=operation)


__all__ = [
    "InjectedWindowsCredentialBackend",
    "InjectedWindowsCredentialRecord",
    "MAX_INJECTED_CREDENTIAL_TOTAL_BYTES",
    "MAX_INJECTED_CREDENTIAL_VALUE_BYTES",
    "WindowsCredentialProtectedValueSource",
    "execute_injected_windows_credential_helper_once",
]
