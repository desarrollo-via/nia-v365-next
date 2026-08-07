"""M86-BI: adapta una fuente dotenv inyectada al backend M81 one-shot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)


def _zeroize(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


class M86BIInjectedDotenvCredentialBackend:
    """Entrega un registro M81 desde una fuente ya inyectada; no conoce rutas."""

    __slots__ = (
        "_closed",
        "_source",
        "_used",
        "backend_close_calls",
        "fetch_calls",
        "source_close_calls",
        "source_open_calls",
        "source_read_calls",
    )

    def __init__(self, *, source: AllowlistedDotenvSource) -> None:
        if type(source) is not AllowlistedDotenvSource:
            raise TypeError("m86bi_source_invalid")
        self._source: AllowlistedDotenvSource | None = source
        self._used = False
        self._closed = False
        self.fetch_calls = 0
        self.source_open_calls = 0
        self.source_read_calls = 0
        self.source_close_calls = 0
        self.backend_close_calls = 0

    async def fetch_exact(self, target_id: str) -> InjectedWindowsCredentialRecord:
        if (
            self._used
            or self._closed
            or self._source is None
            or target_id != M80_CREDENTIAL_TARGET_ID
        ):
            self._used = True
            raise ProtectedSourceOpenFailure("protected_source_contract_invalid")
        self._used = True
        self.fetch_calls = 1
        source, self._source = self._source, None
        buffers: object = {}
        record: InjectedWindowsCredentialRecord | None = None
        cleanup_ok = True
        try:
            self.source_open_calls = 1
            await source.open()
            incoming: dict[str, bytearray] = {}
            for name in PROTECTED_SETTING_NAMES:
                value = await source.read(name)
                self.source_read_calls += 1
                if type(value) is not bytearray or not value or b"\x00" in value:
                    if type(value) is bytearray:
                        value[:] = b"\x00" * len(value)
                    raise ValueError("m86bi_value_invalid")
                incoming[name] = value
            buffers, incoming = incoming, {}
            record = InjectedWindowsCredentialRecord(
                target_id=M80_CREDENTIAL_TARGET_ID,
                buffers=buffers,
            )
            buffers = {}
        except BaseException as error:
            _zeroize(locals().get("incoming"))
            _zeroize(buffers)
            if record is not None:
                record.clear()
                record = None
            if isinstance(error, ProtectedSourceOpenFailure):
                raise
            raise ProtectedSourceOpenFailure(
                "protected_source_contract_invalid"
            ) from error
        finally:
            self.source_close_calls = 1
            try:
                await source.close()
            except BaseException:
                cleanup_ok = False
            if not cleanup_ok:
                _zeroize(buffers)
                if record is not None:
                    record.clear()
                    record = None
        if not cleanup_ok or record is None:
            raise RuntimeError("m86bi_source_cleanup_failed")
        return record

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.backend_close_calls = 1
        source, self._source = self._source, None
        if source is not None:
            self.source_close_calls += 1
            await source.close()

    def __repr__(self) -> str:
        return "M86BIInjectedDotenvCredentialBackend(<redacted>)"


@dataclass(frozen=True)
class M86BIDotenvM81BackendContract:
    phase: Literal["M86-BI"] = "M86-BI"
    state: Literal["FIXTURE-ONLY-INERT"] = "FIXTURE-ONLY-INERT"
    source_must_be_injected: Literal[True] = True
    exact_target_only: Literal[True] = True
    exact_name_budget: Literal[7] = 7
    source_open_budget: Literal[1] = 1
    source_transfer_budget: Literal[1] = 1
    source_close_required: Literal[True] = True
    backend_close_required: Literal[True] = True
    direct_bytearray_transfer: Literal[True] = True
    real_path_factory_present: Literal[False] = False
    credential_write_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    cli_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0


__all__ = [
    "M86BIDotenvM81BackendContract",
    "M86BIInjectedDotenvCredentialBackend",
]
