"""Portable one-shot backend for one exact Azure Key Vault secret."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
    MAX_INJECTED_CREDENTIAL_TOTAL_BYTES,
    MAX_INJECTED_CREDENTIAL_VALUE_BYTES,
)
from .bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)
from .r1_pre_event_activation_preflight import PROTECTED_TARGET_ID


KEY_VAULT_SECRET_NAME = "nia-next-bitrix-r1-protected-settings-v1"
KEY_VAULT_BLOB_MAGIC = b"NIA-NEXT-R1-KEYVAULT-V1\x00"
KEY_VAULT_BLOB_FORMAT = "ordered-name-length-value-v1"
MAX_KEY_VAULT_DECODED_BLOB_BYTES = 18 * 1024
MAX_KEY_VAULT_ENCODED_SECRET_BYTES = 24 * 1024


def _zeroize(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)


class ExactSecretBytesClient(Protocol):
    async def get_secret_bytes_once(self, name: str) -> bytearray: ...

    async def close(self) -> None: ...


def _take_size(blob: bytearray, offset: int, width: int) -> tuple[int, int]:
    end = offset + width
    if end > len(blob):
        raise ValueError("r1_key_vault_blob_truncated")
    return int.from_bytes(blob[offset:end], "big"), end


def _parse_exact_blob(blob: bytearray) -> dict[str, bytearray]:
    if (
        type(blob) is not bytearray
        or len(blob) <= len(KEY_VAULT_BLOB_MAGIC)
        or len(blob) > MAX_KEY_VAULT_DECODED_BLOB_BYTES
        or bytes(blob[: len(KEY_VAULT_BLOB_MAGIC)]) != KEY_VAULT_BLOB_MAGIC
    ):
        raise ValueError("r1_key_vault_blob_header_invalid")
    offset = len(KEY_VAULT_BLOB_MAGIC)
    buffers: dict[str, bytearray] = {}
    try:
        for expected_name in PROTECTED_SETTING_NAMES:
            name_size, offset = _take_size(blob, offset, 2)
            if name_size <= 0 or name_size > 128:
                raise ValueError("r1_key_vault_blob_name_invalid")
            name_end = offset + name_size
            if name_end > len(blob):
                raise ValueError("r1_key_vault_blob_truncated")
            try:
                name = bytes(blob[offset:name_end]).decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError("r1_key_vault_blob_name_invalid") from error
            offset = name_end
            if name != expected_name or name in buffers:
                raise ValueError("r1_key_vault_blob_allowlist_or_order_invalid")
            value_size, offset = _take_size(blob, offset, 4)
            if value_size <= 0 or value_size > MAX_INJECTED_CREDENTIAL_VALUE_BYTES:
                raise ValueError("r1_key_vault_blob_value_size_invalid")
            value_end = offset + value_size
            if value_end > len(blob):
                raise ValueError("r1_key_vault_blob_truncated")
            value = bytearray(blob[offset:value_end])
            offset = value_end
            if b"\x00" in value:
                _zeroize(value)
                raise ValueError("r1_key_vault_blob_value_invalid")
            buffers[name] = value
        if (
            offset != len(blob)
            or sum(map(len, buffers.values()))
            > MAX_INJECTED_CREDENTIAL_TOTAL_BYTES
        ):
            raise ValueError("r1_key_vault_blob_trailing_or_total_invalid")
        return buffers
    except BaseException:
        for value in buffers.values():
            _zeroize(value)
        buffers.clear()
        raise


class AzureKeyVaultExactSecretBackend:
    """M81-compatible backend with one exact get and no list/write surface."""

    __slots__ = ("_client", "_closed", "_used")

    def __init__(self, *, client: ExactSecretBytesClient) -> None:
        if (
            client is None
            or not callable(getattr(client, "get_secret_bytes_once", None))
            or not callable(getattr(client, "close", None))
        ):
            raise TypeError("r1_key_vault_client_invalid")
        self._client: Optional[ExactSecretBytesClient] = client
        self._used = False
        self._closed = False

    async def fetch_exact(self, target_id: str) -> InjectedWindowsCredentialRecord:
        client = self._client
        if (
            self._used
            or self._closed
            or client is None
            or target_id != PROTECTED_TARGET_ID
        ):
            self._used = True
            raise RuntimeError("r1_key_vault_backend_reuse_or_target_invalid")
        self._used = True
        blob = bytearray()
        buffers: dict[str, bytearray] = {}
        try:
            blob = await client.get_secret_bytes_once(KEY_VAULT_SECRET_NAME)
            if type(blob) is not bytearray:
                raise ProtectedSourceOpenFailure("protected_source_blob_invalid")
            try:
                buffers = _parse_exact_blob(blob)
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
        except ProtectedSourceOpenFailure:
            raise
        except Exception as error:
            raise ProtectedSourceOpenFailure(
                "protected_source_record_unavailable"
            ) from error
        finally:
            _zeroize(blob)
            for value in buffers.values():
                _zeroize(value)
            buffers.clear()

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and not self._closed:
            self._closed = True
            await client.close()

    def __repr__(self) -> str:
        return "AzureKeyVaultExactSecretBackend(<redacted>)"


class AzureSDKExactSecretBytesClient:
    """Thin owned adapter; SDK objects are injected and never imported here."""

    __slots__ = ("_client", "_credential", "_used")

    def __init__(self, *, client: object, credential: object) -> None:
        if (
            client is None
            or not callable(getattr(client, "get_secret", None))
            or credential is None
            or not callable(getattr(credential, "close", None))
        ):
            raise TypeError("r1_key_vault_sdk_resources_invalid")
        self._client: Optional[object] = client
        self._credential: Optional[object] = credential
        self._used = False

    async def get_secret_bytes_once(self, name: str) -> bytearray:
        client = self._client
        if self._used or client is None or name != KEY_VAULT_SECRET_NAME:
            self._used = True
            raise RuntimeError("r1_key_vault_sdk_client_reuse_or_name_invalid")
        self._used = True
        response = await client.get_secret(name)
        encoded = getattr(response, "value", None)
        if (
            type(encoded) is not str
            or not encoded
            or len(encoded.encode("ascii", errors="ignore"))
            > MAX_KEY_VAULT_ENCODED_SECRET_BYTES
        ):
            raise ValueError("r1_key_vault_secret_value_invalid")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, UnicodeError) as error:
            raise ValueError("r1_key_vault_secret_value_invalid") from error
        if not raw or len(raw) > MAX_KEY_VAULT_DECODED_BLOB_BYTES:
            raise ValueError("r1_key_vault_secret_value_invalid")
        return bytearray(raw)

    async def close(self) -> None:
        client, self._client = self._client, None
        credential, self._credential = self._credential, None
        failures = 0
        for resource in (client, credential):
            if resource is not None:
                try:
                    await resource.close()
                except BaseException:
                    failures += 1
        if failures:
            raise RuntimeError("r1_key_vault_sdk_resources_close_failed")

    def __repr__(self) -> str:
        return "AzureSDKExactSecretBytesClient(<redacted>)"


class _AzureKeyVaultBindingPermit:
    __slots__ = ()


@dataclass(frozen=True)
class AzureKeyVaultDormantBindingPreview:
    state: Literal["WAITING-EXACT-AUTHORIZATION"] = (
        "WAITING-EXACT-AUTHORIZATION"
    )
    permit_required: Literal[True] = True
    permit_consumed: bool = False
    credential_constructions: int = 0
    client_constructions: int = 0
    secret_reads: Literal[0] = 0
    secret_lists: Literal[0] = 0
    writes: Literal[0] = 0
    external_calls: Literal[0] = 0


class AzureKeyVaultDormantBinding:
    """Builds SDK resources only after a future exact gate permit."""

    __slots__ = (
        "_client_builder",
        "_credential_builder",
        "_permit_consumed",
        "_used",
        "_vault_url",
        "client_constructions",
        "credential_constructions",
    )

    def __init__(self, *, vault_url: str, credential_builder, client_builder) -> None:
        if (
            type(vault_url) is not str
            or not vault_url.startswith("https://")
            or not vault_url.endswith(".vault.azure.net")
            or not callable(credential_builder)
            or not callable(client_builder)
        ):
            raise TypeError("r1_key_vault_binding_dependency_invalid")
        self._vault_url = vault_url
        self._credential_builder = credential_builder
        self._client_builder = client_builder
        self._used = False
        self._permit_consumed = False
        self.credential_constructions = 0
        self.client_constructions = 0

    def __call__(self) -> AzureKeyVaultExactSecretBackend:
        raise RuntimeError("r1_key_vault_binding_permit_required")

    async def build_after_gate_once(
        self, permit: _AzureKeyVaultBindingPermit
    ) -> AzureKeyVaultExactSecretBackend:
        if self._used or type(permit) is not _AzureKeyVaultBindingPermit:
            self._used = True
            raise RuntimeError("r1_key_vault_binding_reuse_or_permit_invalid")
        self._used = True
        self._permit_consumed = True
        credential: object | None = None
        client: object | None = None
        try:
            credential = self._credential_builder()
            self.credential_constructions = 1
            client = self._client_builder(self._vault_url, credential)
            self.client_constructions = 1
            adapter = AzureSDKExactSecretBytesClient(
                client=client,
                credential=credential,
            )
            credential = None
            client = None
            return AzureKeyVaultExactSecretBackend(client=adapter)
        except BaseException as error:
            for resource in (client, credential):
                close = getattr(resource, "close", None)
                if callable(close):
                    try:
                        await close()
                    except BaseException:
                        pass
            raise RuntimeError("r1_key_vault_binding_build_failed") from error
        finally:
            self._credential_builder = None
            self._client_builder = None
            self._vault_url = ""

    def preview(self) -> AzureKeyVaultDormantBindingPreview:
        return AzureKeyVaultDormantBindingPreview(
            permit_consumed=self._permit_consumed,
            credential_constructions=self.credential_constructions,
            client_constructions=self.client_constructions,
        )


def build_dormant_real_key_vault_binding(
    *, vault_url: str
) -> AzureKeyVaultDormantBinding:
    """Defines lazy Azure SDK imports; construction performs no import or call."""

    def credential_builder():
        from azure.identity.aio import DefaultAzureCredential

        return DefaultAzureCredential()

    def client_builder(exact_vault_url: str, credential: object):
        from azure.keyvault.secrets.aio import SecretClient

        return SecretClient(vault_url=exact_vault_url, credential=credential)

    return AzureKeyVaultDormantBinding(
        vault_url=vault_url,
        credential_builder=credential_builder,
        client_builder=client_builder,
    )


__all__ = [
    "AzureKeyVaultDormantBinding",
    "AzureKeyVaultDormantBindingPreview",
    "AzureKeyVaultExactSecretBackend",
    "AzureSDKExactSecretBytesClient",
    "ExactSecretBytesClient",
    "KEY_VAULT_BLOB_FORMAT",
    "KEY_VAULT_BLOB_MAGIC",
    "KEY_VAULT_SECRET_NAME",
    "MAX_KEY_VAULT_DECODED_BLOB_BYTES",
    "MAX_KEY_VAULT_ENCODED_SECRET_BYTES",
    "build_dormant_real_key_vault_binding",
]
