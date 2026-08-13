"""Hermetic one-shot owner for the fixed R1 Key Vault provisioning manifest."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    MAX_INJECTED_CREDENTIAL_TOTAL_BYTES,
    MAX_INJECTED_CREDENTIAL_VALUE_BYTES,
)
from .r1_key_vault_exact_secret_backend import (
    KEY_VAULT_BLOB_MAGIC,
    KEY_VAULT_SECRET_NAME,
    MAX_KEY_VAULT_DECODED_BLOB_BYTES,
    MAX_KEY_VAULT_ENCODED_SECRET_BYTES,
)


MANIFEST_SHA256 = "16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49"
FIRST_CONFIRMATION_TEXT = "sp"
SECOND_CONFIRMATION_TEXT = (
    "SEGUNDA CONFIRMACION R1 KEYVAULT LINUX R1-KV-2026-08-10-V1 "
    "EJECUCION INMEDIATA "
    + MANIFEST_SHA256
)

SUBSCRIPTION_ID = "0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9"
RESOURCE_GROUP = "nia-v365-next-api_group"
WEB_APP_NAME = "nia-v365-next-api"
WEB_APP_ID = (
    "/subscriptions/0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9/"
    "resourceGroups/nia-v365-next-api_group/providers/Microsoft.Web/"
    "sites/nia-v365-next-api"
)
VAULT_NAME = "nia-next-r1-kv-260810"
VAULT_ID = (
    "/subscriptions/0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9/"
    "resourceGroups/nia-v365-next-api_group/providers/Microsoft.KeyVault/"
    "vaults/nia-next-r1-kv-260810"
)
VAULT_URL = "https://nia-next-r1-kv-260810.vault.azure.net/"
ROLE_DEFINITION_ID = "4633458b-17de-408a-b874-0445c86b69e6"
ROLE_ASSIGNMENT_ID = "eb70d2d7-bfe7-49ed-8ccc-0fd43d1c6447"
WRITER_ROLE_DEFINITION_ID = "b86a8fe4-44ce-4948-aee5-eccb2c155cd7"
WRITER_ROLE_ASSIGNMENT_ID = "5e76b332-d208-4129-9ad2-cc760bb23d1f"
APP_SETTING_NAME = "NIA_BITRIX_KEY_VAULT_URL"


def _zeroize(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)


def _zeroize_buffers(buffers: dict[str, bytearray]) -> None:
    for value in buffers.values():
        _zeroize(value)
    buffers.clear()


class KeyVaultSecretPayloadOwner:
    """Owns one encoded secret buffer and never represents its contents."""

    __slots__ = ("_closed", "_payload", "_taken")

    def __init__(self, payload: bytearray) -> None:
        if type(payload) is not bytearray or not payload:
            raise TypeError("r1_kv_provisioning_payload_invalid")
        self._payload = payload
        self._taken = False
        self._closed = False

    def take_once(self) -> bytearray:
        if self._taken or self._closed:
            raise RuntimeError("r1_kv_provisioning_payload_unavailable")
        self._taken = True
        payload, self._payload = self._payload, bytearray()
        return payload

    def close(self) -> None:
        _zeroize(self._payload)
        self._payload = bytearray()
        self._closed = True

    def __repr__(self) -> str:
        return "KeyVaultSecretPayloadOwner(<redacted>)"


def materialize_key_vault_secret_payload(
    buffers: dict[str, bytearray],
) -> KeyVaultSecretPayloadOwner:
    """Serializes the exact allowlist without opening any protected source."""

    if type(buffers) is not dict or tuple(buffers) != PROTECTED_SETTING_NAMES:
        raise ValueError("r1_kv_provisioning_allowlist_or_order_invalid")
    raw = bytearray(KEY_VAULT_BLOB_MAGIC)
    encoded = bytearray()
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
                raise ValueError("r1_kv_provisioning_value_invalid")
            total += len(value)
            name_bytes = name.encode("ascii")
            raw.extend(len(name_bytes).to_bytes(2, "big"))
            raw.extend(name_bytes)
            raw.extend(len(value).to_bytes(4, "big"))
            raw.extend(value)
        if total > MAX_INJECTED_CREDENTIAL_TOTAL_BYTES:
            raise ValueError("r1_kv_provisioning_payload_too_large")
        if len(raw) > MAX_KEY_VAULT_DECODED_BLOB_BYTES:
            raise ValueError("r1_kv_provisioning_payload_too_large")
        encoded.extend(base64.b64encode(raw))
        if not encoded or len(encoded) > MAX_KEY_VAULT_ENCODED_SECRET_BYTES:
            raise ValueError("r1_kv_provisioning_payload_too_large")
        owner = KeyVaultSecretPayloadOwner(encoded)
        encoded = bytearray()
        return owner
    finally:
        _zeroize(raw)
        _zeroize(encoded)


@dataclass(frozen=True)
class AzureProvisioningPreflightEvidence:
    manifest_sha256: str = MANIFEST_SHA256
    subscription_id: str = SUBSCRIPTION_ID
    resource_group: str = RESOURCE_GROUP
    web_app_id: str = WEB_APP_ID
    web_app_running: bool = True
    linux_python_312: bool = True
    identity_absent: bool = True
    vault_absent: bool = True
    vault_name_available: bool = True
    app_setting_absent: bool = True
    role_definition_id: str = ROLE_DEFINITION_ID
    writer_role_definition_id: str = WRITER_ROLE_DEFINITION_ID
    operator_principal_id: str = "a22738d4-9a45-4235-aa31-a4c57272a064"
    dormant_health_stable: bool = True
    connector_v0267_off_locked_inert: bool = True
    local_state_preserved: bool = True
    writes: int = 0
    retries: int = 0

    @property
    def exact(self) -> bool:
        expected = AzureProvisioningPreflightEvidence()
        try:
            operator_valid = uuid.UUID(self.operator_principal_id).int != 0
        except (AttributeError, TypeError, ValueError):
            operator_valid = False
        return operator_valid and replace(
            self,
            operator_principal_id=expected.operator_principal_id,
        ) == expected


class ProtectedValueSource(Protocol):
    async def open(self) -> None: ...

    async def read(self, name: str) -> bytearray: ...

    async def close(self) -> None: ...


class ExactSecretSink(Protocol):
    async def set_exact_secret_once(self, payload: bytearray) -> str: ...

    async def close(self) -> None: ...


class ExactAzureProvisioningPort(Protocol):
    async def preflight_exact_once(self) -> AzureProvisioningPreflightEvidence: ...

    async def create_exact_vault_once(self) -> str: ...

    async def enable_exact_system_identity_once(self) -> str: ...

    async def create_exact_role_assignment_once(self, principal_id: str) -> str: ...

    async def create_exact_writer_role_assignment_once(self) -> str: ...

    async def delete_exact_writer_role_assignment_once(self) -> None: ...

    async def set_exact_app_setting_once(self) -> None: ...

    async def verify_exact_dormant_health_once(self) -> bool: ...

    async def remove_exact_app_setting_once(self) -> None: ...

    async def delete_exact_role_assignment_once(self) -> None: ...

    async def disable_exact_system_identity_once(self) -> None: ...

    async def soft_delete_exact_vault_once(self) -> None: ...

    async def verify_exact_vault_rollback_once(self) -> bool: ...

    async def close(self) -> None: ...


ProvisioningState = Literal[
    "INERT",
    "NO-GO-FIRST-CONFIRMATION",
    "NO-GO-PREFLIGHT",
    "AWAITING-SECOND-CONFIRMATION",
    "NO-GO-SECOND-CONFIRMATION",
    "PROVISIONED-DORMANT-VERIFIED",
    "FAILED-RESTORED",
    "NO-GO-REMAINDER",
]


@dataclass(frozen=True)
class R1KeyVaultLinuxProvisioningSnapshot:
    state: ProvisioningState = "INERT"
    manifest_sha256: Literal[
        "16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49"
    ] = MANIFEST_SHA256
    first_confirmation_exact: bool = False
    second_confirmation_exact: bool = False
    first_confirmation_consumed: bool = False
    second_confirmation_consumed: bool = False
    failure_stage: str = "none"
    failure_category: str = "none"
    preflight_calls: int = 0
    vault_create_calls: int = 0
    identity_enable_calls: int = 0
    role_assignment_create_calls: int = 0
    writer_role_assignment_create_calls: int = 0
    writer_role_assignment_delete_calls: int = 0
    protected_source_open_calls: int = 0
    protected_source_read_calls: int = 0
    secret_write_calls: int = 0
    app_setting_write_calls: int = 0
    dormant_health_calls: int = 0
    rollback_calls: int = 0
    vault_rollback_postread_calls: int = 0
    rollback_complete: bool = False
    resources_closed: bool = False
    retries: Literal[0] = 0
    secret_lists: Literal[0] = 0
    app_setting_lists: Literal[0] = 0
    broad_resource_lists: Literal[0] = 0
    real_binding_present: bool = False
    r1_activated: Literal[False] = False
    bitrix_calls: Literal[0] = 0
    messages_sent: Literal[0] = 0


class R1KeyVaultLinuxProvisioningOwner:
    """Two-gate owner with reverse rollback and no concrete external binding."""

    __slots__ = (
        "_control",
        "_control_closed",
        "_counts",
        "_prepared",
        "_real_binding_present",
        "_sink",
        "_sink_closed",
        "_source",
        "_source_closed",
        "_used",
    )

    def __init__(
        self,
        *,
        control: ExactAzureProvisioningPort,
        source: ProtectedValueSource,
        sink: ExactSecretSink,
        real_binding_present: bool = False,
    ) -> None:
        required_control = (
            "preflight_exact_once",
            "create_exact_vault_once",
            "enable_exact_system_identity_once",
            "create_exact_role_assignment_once",
            "create_exact_writer_role_assignment_once",
            "delete_exact_writer_role_assignment_once",
            "set_exact_app_setting_once",
            "verify_exact_dormant_health_once",
            "remove_exact_app_setting_once",
            "delete_exact_role_assignment_once",
            "disable_exact_system_identity_once",
            "soft_delete_exact_vault_once",
            "verify_exact_vault_rollback_once",
            "close",
        )
        if any(not callable(getattr(control, name, None)) for name in required_control):
            raise TypeError("r1_kv_provisioning_control_invalid")
        if any(not callable(getattr(source, name, None)) for name in ("open", "read", "close")):
            raise TypeError("r1_kv_provisioning_source_invalid")
        if any(not callable(getattr(sink, name, None)) for name in ("set_exact_secret_once", "close")):
            raise TypeError("r1_kv_provisioning_sink_invalid")
        self._control: ExactAzureProvisioningPort | None = control
        self._source: ProtectedValueSource | None = source
        self._sink: ExactSecretSink | None = sink
        if type(real_binding_present) is not bool:
            raise TypeError("r1_kv_provisioning_real_binding_flag_invalid")
        self._real_binding_present = real_binding_present
        self._control_closed = False
        self._source_closed = False
        self._sink_closed = False
        self._prepared = False
        self._used = False
        self._counts = {
            "preflight_calls": 0,
            "vault_create_calls": 0,
            "identity_enable_calls": 0,
            "role_assignment_create_calls": 0,
            "writer_role_assignment_create_calls": 0,
            "writer_role_assignment_delete_calls": 0,
            "protected_source_open_calls": 0,
            "protected_source_read_calls": 0,
            "secret_write_calls": 0,
            "app_setting_write_calls": 0,
            "dormant_health_calls": 0,
            "rollback_calls": 0,
            "vault_rollback_postread_calls": 0,
        }

    def __repr__(self) -> str:
        return "R1KeyVaultLinuxProvisioningOwner(<redacted>)"

    def preview(self) -> R1KeyVaultLinuxProvisioningSnapshot:
        return self._snapshot(state="INERT")

    def _snapshot(
        self,
        *,
        state: ProvisioningState,
        first_exact: bool = False,
        second_exact: bool = False,
        first_consumed: bool = False,
        second_consumed: bool = False,
        rollback_complete: bool = False,
        resources_closed: bool = False,
        failure_stage: str = "none",
        failure_category: str = "none",
    ) -> R1KeyVaultLinuxProvisioningSnapshot:
        return R1KeyVaultLinuxProvisioningSnapshot(
            state=state,
            first_confirmation_exact=first_exact,
            second_confirmation_exact=second_exact,
            first_confirmation_consumed=first_consumed,
            second_confirmation_consumed=second_consumed,
            rollback_complete=rollback_complete,
            resources_closed=resources_closed,
            failure_stage=failure_stage,
            failure_category=failure_category,
            real_binding_present=self._real_binding_present,
            **self._counts,
        )

    async def _close_private_once(self) -> bool:
        failures = 0
        source, self._source = self._source, None
        if source is not None and not self._source_closed:
            self._source_closed = True
            try:
                await source.close()
            except BaseException:
                failures += 1
        sink, self._sink = self._sink, None
        if sink is not None and not self._sink_closed:
            self._sink_closed = True
            try:
                await sink.close()
            except BaseException:
                failures += 1
        return failures == 0

    async def _close_control_once(self) -> bool:
        control, self._control = self._control, None
        if control is None or self._control_closed:
            return True
        self._control_closed = True
        try:
            await control.close()
        except BaseException:
            return False
        return True

    async def _close_all_once(self) -> bool:
        private_ok = await self._close_private_once()
        control_ok = await self._close_control_once()
        return private_ok and control_ok

    async def prepare_once(
        self, *, first_confirmation: str
    ) -> R1KeyVaultLinuxProvisioningSnapshot:
        if self._used:
            raise RuntimeError("r1_kv_provisioning_owner_reused")
        self._used = True
        exact = (
            type(first_confirmation) is str
            and first_confirmation.casefold() == FIRST_CONFIRMATION_TEXT
        )
        if not exact:
            closed = await self._close_all_once()
            return self._snapshot(
                state="NO-GO-FIRST-CONFIRMATION",
                first_consumed=True,
                resources_closed=closed,
            )
        control = self._control
        if control is None:
            raise RuntimeError("r1_kv_provisioning_control_unavailable")
        self._counts["preflight_calls"] = 1
        try:
            evidence = await control.preflight_exact_once()
            if type(evidence) is not AzureProvisioningPreflightEvidence or not evidence.exact:
                raise RuntimeError("r1_kv_provisioning_preflight_drift")
        except BaseException:
            closed = await self._close_all_once()
            return self._snapshot(
                state="NO-GO-PREFLIGHT",
                first_exact=True,
                first_consumed=True,
                resources_closed=closed,
            )
        self._prepared = True
        return self._snapshot(
            state="AWAITING-SECOND-CONFIRMATION",
            first_exact=True,
            first_consumed=True,
        )

    async def _rollback(
        self,
        *,
        vault_attempted: bool,
        identity_attempted: bool,
        role_attempted: bool,
        writer_attempted: bool,
        writer_cleanup_attempted: bool,
        setting_attempted: bool,
    ) -> bool:
        control = self._control
        if control is None:
            return not any(
                (vault_attempted, identity_attempted, role_attempted, writer_attempted, setting_attempted)
            )
        ok = True
        actions = (
            (setting_attempted, control.remove_exact_app_setting_once),
            (
                writer_attempted and not writer_cleanup_attempted,
                control.delete_exact_writer_role_assignment_once,
            ),
            (role_attempted, control.delete_exact_role_assignment_once),
            (identity_attempted, control.disable_exact_system_identity_once),
            (vault_attempted, control.soft_delete_exact_vault_once),
        )
        for required, action in actions:
            if not required:
                continue
            self._counts["rollback_calls"] += 1
            try:
                await action()
            except BaseException:
                ok = False
        if vault_attempted:
            self._counts["vault_rollback_postread_calls"] = 1
            try:
                if await control.verify_exact_vault_rollback_once() is not True:
                    ok = False
            except BaseException:
                ok = False
        return ok

    async def execute_once(
        self, *, second_confirmation: str
    ) -> R1KeyVaultLinuxProvisioningSnapshot:
        if not self._prepared:
            raise RuntimeError("r1_kv_provisioning_owner_not_prepared")
        self._prepared = False
        exact = type(second_confirmation) is str and second_confirmation == SECOND_CONFIRMATION_TEXT
        if not exact:
            closed = await self._close_all_once()
            return self._snapshot(
                state="NO-GO-SECOND-CONFIRMATION",
                first_exact=True,
                first_consumed=True,
                second_consumed=True,
                resources_closed=closed,
            )

        control = self._control
        source = self._source
        sink = self._sink
        if control is None or source is None or sink is None:
            raise RuntimeError("r1_kv_provisioning_dependencies_unavailable")

        vault_attempted = False
        identity_attempted = False
        role_attempted = False
        writer_attempted = False
        writer_cleanup_attempted = False
        setting_attempted = False
        operation_ok = False
        failure_stage = "none"
        failure_category = "none"
        private_ok = False
        buffers: dict[str, bytearray] = {}
        payload_owner: KeyVaultSecretPayloadOwner | None = None
        payload = bytearray()
        try:
            failure_stage = "vault_create"
            vault_attempted = True
            self._counts["vault_create_calls"] = 1
            if await control.create_exact_vault_once() != VAULT_ID:
                raise RuntimeError("r1_kv_provisioning_vault_identity_drift")

            failure_stage = "identity_enable"
            identity_attempted = True
            self._counts["identity_enable_calls"] = 1
            principal_id = await control.enable_exact_system_identity_once()
            try:
                uuid.UUID(principal_id)
            except (AttributeError, TypeError, ValueError) as error:
                raise RuntimeError("r1_kv_provisioning_principal_invalid") from error

            failure_stage = "reader_role_create"
            role_attempted = True
            self._counts["role_assignment_create_calls"] = 1
            assignment_id = await control.create_exact_role_assignment_once(principal_id)
            if assignment_id != ROLE_ASSIGNMENT_ID:
                raise RuntimeError("r1_kv_provisioning_assignment_identity_drift")

            failure_stage = "writer_role_create"
            writer_attempted = True
            self._counts["writer_role_assignment_create_calls"] = 1
            writer_assignment_id = await control.create_exact_writer_role_assignment_once()
            if writer_assignment_id != WRITER_ROLE_ASSIGNMENT_ID:
                raise RuntimeError("r1_kv_provisioning_writer_assignment_drift")

            failure_stage = "protected_source_open"
            self._counts["protected_source_open_calls"] = 1
            await source.open()
            for name in PROTECTED_SETTING_NAMES:
                failure_stage = "protected_source_read"
                self._counts["protected_source_read_calls"] += 1
                value = await source.read(name)
                if type(value) is not bytearray or not value:
                    raise RuntimeError("r1_kv_provisioning_protected_value_invalid")
                buffers[name] = value
            payload_owner = materialize_key_vault_secret_payload(buffers)
            payload = payload_owner.take_once()

            failure_stage = "secret_write"
            self._counts["secret_write_calls"] = 1
            secret_version_id = await sink.set_exact_secret_once(payload)
            if type(secret_version_id) is not str or not secret_version_id:
                raise RuntimeError("r1_kv_provisioning_secret_version_invalid")

            _zeroize(payload)
            payload = bytearray()
            payload_owner.close()
            payload_owner = None
            _zeroize_buffers(buffers)
            private_ok = await self._close_private_once()
            if not private_ok:
                raise RuntimeError("r1_kv_provisioning_private_close_failed")

            failure_stage = "writer_role_delete"
            writer_cleanup_attempted = True
            self._counts["writer_role_assignment_delete_calls"] = 1
            await control.delete_exact_writer_role_assignment_once()

            failure_stage = "app_setting_write"
            setting_attempted = True
            self._counts["app_setting_write_calls"] = 1
            await control.set_exact_app_setting_once()
            failure_stage = "dormant_health"
            self._counts["dormant_health_calls"] = 1
            if await control.verify_exact_dormant_health_once() is not True:
                raise RuntimeError("r1_kv_provisioning_health_drift")
            operation_ok = True
            failure_stage = "none"
        except BaseException as error:
            operation_ok = False
            code = str(error)
            failure_category = next(
                (
                    category
                    for category in (
                        "authentication", "authorization", "not_found",
                        "transport", "unknown",
                    )
                    if code.endswith("_" + category)
                ),
                "drift" if "drift" in code else "invalid_evidence",
            )
        finally:
            _zeroize(payload)
            if payload_owner is not None:
                payload_owner.close()
            _zeroize_buffers(buffers)
            if not self._source_closed or not self._sink_closed:
                private_ok = await self._close_private_once()

        rollback_complete = False
        if not operation_ok or not private_ok:
            rollback_complete = await self._rollback(
                vault_attempted=vault_attempted,
                identity_attempted=identity_attempted,
                role_attempted=role_attempted,
                writer_attempted=writer_attempted,
                writer_cleanup_attempted=writer_cleanup_attempted,
                setting_attempted=setting_attempted,
            )
        control_ok = await self._close_control_once()
        resources_closed = private_ok and control_ok

        if operation_ok and private_ok and control_ok:
            state: ProvisioningState = "PROVISIONED-DORMANT-VERIFIED"
        elif rollback_complete and resources_closed:
            state = "FAILED-RESTORED"
        else:
            state = "NO-GO-REMAINDER"
        return self._snapshot(
            state=state,
            first_exact=True,
            second_exact=True,
            first_consumed=True,
            second_consumed=True,
            rollback_complete=rollback_complete,
            resources_closed=resources_closed,
            failure_stage=failure_stage,
            failure_category=failure_category,
        )


__all__ = [
    "APP_SETTING_NAME",
    "AzureProvisioningPreflightEvidence",
    "ExactAzureProvisioningPort",
    "ExactSecretSink",
    "FIRST_CONFIRMATION_TEXT",
    "KeyVaultSecretPayloadOwner",
    "MANIFEST_SHA256",
    "RESOURCE_GROUP",
    "R1KeyVaultLinuxProvisioningOwner",
    "R1KeyVaultLinuxProvisioningSnapshot",
    "ROLE_ASSIGNMENT_ID",
    "ROLE_DEFINITION_ID",
    "SECOND_CONFIRMATION_TEXT",
    "SUBSCRIPTION_ID",
    "VAULT_ID",
    "VAULT_NAME",
    "VAULT_URL",
    "WEB_APP_ID",
    "WEB_APP_NAME",
    "WRITER_ROLE_ASSIGNMENT_ID",
    "WRITER_ROLE_DEFINITION_ID",
    "materialize_key_vault_secret_payload",
]
