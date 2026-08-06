"""Contrato M86-U y serializador M84 puro, sin acceso al sistema operativo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    MAX_INJECTED_CREDENTIAL_TOTAL_BYTES,
    MAX_INJECTED_CREDENTIAL_VALUE_BYTES,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    M84_BLOB_FORMAT,
    M84_BLOB_MAGIC,
    MAX_M84_BLOB_BYTES,
)
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


def _zeroize(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)


class M84MaterializedBlobOwner:
    """Custodia un blob construido en memoria y lo entrega una sola vez."""

    __slots__ = ("_blob", "_closed", "_taken")

    def __init__(self, blob: bytearray) -> None:
        if type(blob) is not bytearray or not blob:
            raise TypeError("m86_materialized_blob_invalid")
        self._blob = blob
        self._closed = False
        self._taken = False

    def __repr__(self) -> str:
        return "M84MaterializedBlobOwner(<redacted>)"

    def take_blob_once(self) -> bytearray:
        if self._closed or self._taken:
            raise RuntimeError("m86_materialized_blob_unavailable")
        self._taken = True
        blob, self._blob = self._blob, bytearray()
        return blob

    def close(self) -> None:
        _zeroize(self._blob)
        self._blob = bytearray()
        self._closed = True


def materialize_m84_blob_from_injected_buffers(
    buffers: dict[str, bytearray],
) -> M84MaterializedBlobOwner:
    """Serializa buffers ya inyectados; no abre ni consulta ninguna fuente."""

    if type(buffers) is not dict or tuple(buffers) != PROTECTED_SETTING_NAMES:
        raise ValueError("m86_materialization_allowlist_or_order_invalid")

    blob = bytearray()
    try:
        total = 0
        for name in PROTECTED_SETTING_NAMES:
            value = buffers[name]
            if (
                type(value) is not bytearray
                or not value
                or len(value) > MAX_INJECTED_CREDENTIAL_VALUE_BYTES
                or b"\x00" in value
            ):
                raise ValueError("m86_materialization_value_invalid")
            total += len(value)
        if total > MAX_INJECTED_CREDENTIAL_TOTAL_BYTES:
            raise ValueError("m86_materialization_total_invalid")

        blob.extend(M84_BLOB_MAGIC)
        for name in PROTECTED_SETTING_NAMES:
            encoded_name = name.encode("ascii")
            value = buffers[name]
            blob.extend(len(encoded_name).to_bytes(2, "big"))
            blob.extend(encoded_name)
            blob.extend(len(value).to_bytes(4, "big"))
            blob.extend(value)
        if len(blob) > MAX_M84_BLOB_BYTES:
            raise ValueError("m86_materialization_blob_too_large")
        return M84MaterializedBlobOwner(blob)
    except BaseException:
        _zeroize(blob)
        raise


@dataclass(frozen=True)
class M86CredentialMaterializationContract:
    phase: Literal["M86-U"] = "M86-U"
    state: Literal["PREPARED-INERT"] = "PREPARED-INERT"
    target_id: Literal["nia-next/bitrix-r1/protected-settings/v1"] = (
        M80_CREDENTIAL_TARGET_ID
    )
    blob_format: Literal["ordered-name-length-value-v1"] = M84_BLOB_FORMAT
    allowed_names: tuple[str, ...] = PROTECTED_SETTING_NAMES
    serializer_present: Literal[True] = True
    real_value_source_bound: Literal[False] = False
    operating_system_writer_present: Literal[False] = False
    operating_system_delete_present: Literal[False] = False
    preflight_read_budget: Literal[0] = 0
    credential_write_budget: Literal[0] = 0
    credential_delete_budget: Literal[0] = 0
    credential_enumeration_budget: Literal[0] = 0
    external_call_budget: Literal[0] = 0
    two_separate_confirmations_required: Literal[True] = True
    exact_preflight_required: Literal[True] = True
    ambiguous_prior_state_is_no_go: Literal[True] = True
    rollback_if_prior_absent: Literal["delete_only_new_exact_target"] = (
        "delete_only_new_exact_target"
    )
    rollback_if_prior_present: Literal["restore_exact_protected_prior_blob"] = (
        "restore_exact_protected_prior_blob"
    )
    rollback_implementation_present: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        if self.allowed_names != PROTECTED_SETTING_NAMES:
            raise ValueError("m86_materialization_contract_invalid")


def inspect_m86_credential_materialization_contract(
) -> M86CredentialMaterializationContract:
    """Devuelve sólo metadatos públicos; no materializa ni abre recursos."""

    return M86CredentialMaterializationContract()


__all__ = [
    "M84MaterializedBlobOwner",
    "M86CredentialMaterializationContract",
    "inspect_m86_credential_materialization_contract",
    "materialize_m84_blob_from_injected_buffers",
]
