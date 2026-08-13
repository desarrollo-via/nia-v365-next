"""Owner transaccional para recuperar y reanudar la provisión R1 exacta."""

from __future__ import annotations

import asyncio
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    WindowsCredentialProtectedValueSource,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from .r1_key_vault_linux_provisioning_owner import (
    ROLE_ASSIGNMENT_ID,
    ROLE_DEFINITION_ID,
    SUBSCRIPTION_ID,
    VAULT_ID,
    VAULT_URL,
    WRITER_ROLE_ASSIGNMENT_ID,
    WRITER_ROLE_DEFINITION_ID,
    materialize_key_vault_secret_payload,
)
from .r1_key_vault_linux_provisioning_real_binding import (
    ACCOUNT_SHOW,
    APP_SETTING_DELETE,
    APP_SETTING_SET,
    AzureKeyVaultExactSecretSink,
    ExactAzureCliCommandRunner,
    ExactDormantHealthReader,
    IDENTITY_DISABLE,
    IDENTITY_ENABLE,
    OPERATOR_SHOW,
    ROLE_DELETE,
    VAULT_DELETED_SHOW,
    VAULT_DELETE,
    VAULT_ACTIVE_ARM_SHOW,
    VAULT_RECOVER,
    VAULT_SHOW,
    VAULT_WAIT_RECOVERED,
    WEB_APP_SHOW,
    WEB_APP_ID,
    WRITER_ROLE_DELETE,
    _role_create,
    _successful,
)
from .r1_key_vault_exact_secret_backend import KEY_VAULT_SECRET_NAME


RBAC_PROPAGATION_SECONDS = 45
MAX_SECRET_PROBES = 3
SECRET_PROBE_RETRY_SECONDS = 30
MAX_DATA_PLANE_PROBES = 120
DATA_PLANE_PROBE_INTERVAL_SECONDS = 15


def _validate_real_runtime_dependencies() -> None:
    """Falla localmente antes de la primera lectura o mutación Azure."""

    for module_name in ("azure.identity.aio", "azure.keyvault.secrets.aio"):
        try:
            importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            raise RuntimeError("r1_recovery_runtime_dependency_missing") from None


def _zeroize(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)


def _zeroize_mapping(values: dict[str, bytearray]) -> None:
    for value in values.values():
        _zeroize(value)
    values.clear()


def _is_explicit_secret_not_found(error: BaseException) -> bool:
    """Reconoce sólo el código de servicio exacto, sin conservar cuerpo ni mensaje."""

    try:
        from azure.core.exceptions import ResourceNotFoundError
    except ImportError:
        ResourceNotFoundError = ()
    if isinstance(error, ResourceNotFoundError):
        return True

    candidates = []
    current = error
    for _ in range(3):
        candidates.append(getattr(current, "code", None))
        current = getattr(current, "error", None)
        if current is None:
            break

    response = getattr(error, "response", None)
    text_reader = getattr(response, "text", None)
    if callable(text_reader):
        body = None
        payload = None
        try:
            body = text_reader()
            if type(body) is str and len(body) <= 16_384:
                payload = json.loads(body)
                if type(payload) is dict:
                    detail = payload.get("error")
                    if type(detail) is dict:
                        candidates.append(detail.get("code"))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        finally:
            body = None
            payload = None

    return any(
        type(code) is str
        and code.casefold() in {"secretnotfound", "secret_not_found"}
        for code in candidates
    )


class ExactSecretExistenceProbe:
    """Una lectura exacta; nunca devuelve ni representa el valor."""

    __slots__ = ("_calls", "_client", "_credential")

    def __init__(self) -> None:
        self._client = None
        self._credential = None
        self._calls = 0

    async def exists_once(self) -> bool:
        if self._calls >= MAX_SECRET_PROBES:
            raise RuntimeError("r1_recovery_secret_probe_reused")
        self._calls += 1
        try:
            from azure.identity.aio import AzureCliCredential
            from azure.keyvault.secrets.aio import SecretClient

            if self._credential is None:
                self._credential = AzureCliCredential()
            if self._client is None:
                self._client = SecretClient(
                    vault_url=VAULT_URL, credential=self._credential
                )
            response = await self._client.get_secret(KEY_VAULT_SECRET_NAME)
        except Exception as error:
            status = getattr(error, "status_code", None)
            if status is None:
                status = getattr(getattr(error, "response", None), "status_code", None)
            name = type(error).__name__.casefold()
            if _is_explicit_secret_not_found(error):
                return False
            category = (
                "authentication" if status == 401 or "authentication" in name or "credentialunavailable" in name
                else "authorization" if status == 403 or "forbidden" in name
                else "not_found" if status == 404 or "notfound" in name
                else "transport" if status in {408, 429, 500, 502, 503, 504}
                or "transport" in name or "timeout" in name
                else "unknown"
            )
            raise RuntimeError(f"r1_recovery_secret_probe_failed_{category}") from None
        secret_name = getattr(response, "name", None)
        if secret_name != KEY_VAULT_SECRET_NAME:
            raise RuntimeError("r1_recovery_secret_probe_invalid")
        response = None
        return True

    async def close(self) -> None:
        client, self._client = self._client, None
        credential, self._credential = self._credential, None
        for resource in (client, credential):
            close = getattr(resource, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result


class ExactBearerSecretExistenceProbe:
    """GET autenticado exacto que evita el challenge y nunca expone valores."""

    __slots__ = ("_calls", "_client", "_client_factory", "_credential", "_credential_factory")

    def __init__(self, *, credential_factory=None, client_factory=httpx.AsyncClient) -> None:
        self._credential_factory = credential_factory
        self._client_factory = client_factory
        self._credential = None
        self._client = None
        self._calls = 0

    async def exists_once(self) -> bool:
        if self._calls:
            raise RuntimeError("r1_bearer_secret_probe_reused")
        self._calls = 1
        token_value = ""
        try:
            if self._credential_factory is None:
                from azure.identity.aio import AzureCliCredential
                self._credential_factory = AzureCliCredential
            self._credential = self._credential_factory()
            token = await self._credential.get_token("https://vault.azure.net/.default")
            token_value = getattr(token, "token", "")
            if type(token_value) is not str or not token_value:
                raise RuntimeError("r1_bearer_secret_probe_authentication")
            self._client = self._client_factory(
                timeout=30, follow_redirects=False, trust_env=False
            )
            url = f"{VAULT_URL}secrets/{KEY_VAULT_SECRET_NAME}?api-version=7.5"
            async with self._client.stream(
                "GET", url, headers={"Authorization": f"Bearer {token_value}"}
            ) as response:
                if response.status_code == 200:
                    return True
                if response.status_code == 404:
                    body = await response.aread()
                    if len(body) <= 4096:
                        try:
                            payload = json.loads(body.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            payload = None
                        detail = payload.get("error") if type(payload) is dict else None
                        code = detail.get("code") if type(detail) is dict else None
                        body = b""
                        payload = detail = None
                        if type(code) is str and code.casefold() in {
                            "secretnotfound", "secret_not_found"
                        }:
                            return False
                    raise RuntimeError("r1_bearer_secret_probe_not_found")
                category = (
                    "authentication" if response.status_code == 401
                    else "authorization" if response.status_code == 403
                    else "transport" if response.status_code in {408, 429, 500, 502, 503, 504}
                    else "unknown"
                )
                raise RuntimeError(f"r1_bearer_secret_probe_{category}")
        finally:
            token_value = ""

    async def close(self) -> None:
        client, self._client = self._client, None
        credential, self._credential = self._credential, None
        for resource in (client, credential):
            close = getattr(resource, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result


class ExactBearerSecretSink:
    """PUT bearer one-shot; no usa el challenge del SDK ni lee la respuesta."""

    __slots__ = ("_calls", "_client", "_client_factory", "_credential", "_credential_factory")

    def __init__(self, *, credential_factory=None, client_factory=httpx.AsyncClient) -> None:
        self._credential_factory = credential_factory
        self._client_factory = client_factory
        self._credential = None
        self._client = None
        self._calls = 0

    async def set_exact_secret_once(self, payload: bytearray) -> str:
        if self._calls or type(payload) is not bytearray or not payload:
            self._calls = 1
            raise RuntimeError("r1_bearer_secret_write_payload_invalid")
        self._calls = 1
        token_value = ""
        request_body = bytearray()
        try:
            if self._credential_factory is None:
                from azure.identity.aio import AzureCliCredential
                self._credential_factory = AzureCliCredential
            self._credential = self._credential_factory()
            token = await self._credential.get_token("https://vault.azure.net/.default")
            token_value = getattr(token, "token", "")
            if type(token_value) is not str or not token_value:
                raise RuntimeError("r1_bearer_secret_write_authentication")
            request_body.extend(b'{"value":"')
            request_body.extend(payload)
            request_body.extend(b'"}')

            async def stream_body():
                yield bytes(request_body)

            self._client = self._client_factory(
                timeout=30, follow_redirects=False, trust_env=False
            )
            url = f"{VAULT_URL}secrets/{KEY_VAULT_SECRET_NAME}?api-version=7.5"
            async with self._client.stream(
                "PUT",
                url,
                headers={
                    "Authorization": f"Bearer {token_value}",
                    "Content-Type": "application/json",
                },
                content=stream_body(),
            ) as response:
                if response.status_code in {200, 201}:
                    return f"{VAULT_URL}secrets/{KEY_VAULT_SECRET_NAME}"
                category = (
                    "authentication" if response.status_code == 401
                    else "authorization" if response.status_code == 403
                    else "not_found" if response.status_code == 404
                    else "transport" if response.status_code in {408, 429, 500, 502, 503, 504}
                    else "unknown"
                )
                raise RuntimeError(f"r1_bearer_secret_write_{category}")
        finally:
            token_value = ""
            _zeroize(request_body)

    async def close(self) -> None:
        client, self._client = self._client, None
        credential, self._credential = self._credential, None
        for resource in (client, credential):
            close = getattr(resource, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result


class ExactVaultDataPlaneReadinessProbe:
    """Consulta sólo la raíz HTTPS exacta; nunca usa rutas de objetos."""

    __slots__ = (
        "_calls", "_client", "last_status_code", "region_header_present",
        "request_id_header_present",
    )

    def __init__(self) -> None:
        self._calls = 0
        self._client = None
        self.last_status_code = 0
        self.region_header_present = False
        self.request_id_header_present = False

    async def ready_once(self) -> bool:
        if self._calls >= MAX_DATA_PLANE_PROBES:
            raise RuntimeError("r1_recovery_data_plane_probe_budget_exhausted")
        self._calls += 1
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=15, follow_redirects=False, trust_env=False
            )
        try:
            response = await self._client.get(VAULT_URL)
        except (httpx.TimeoutException, httpx.TransportError):
            return False
        region = response.headers.get("x-ms-keyvault-region", "")
        request_id = response.headers.get("x-ms-request-id", "")
        self.last_status_code = response.status_code
        self.region_header_present = bool(type(region) is str and region.strip())
        self.request_id_header_present = bool(
            type(request_id) is str and request_id.strip()
        )
        return bool(
            response.status_code in {400, 401, 403, 404}
            and response.url == httpx.URL(VAULT_URL)
            and len(response.content) <= 4096
            and self.region_header_present
            and self.request_id_header_present
        )

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


@dataclass(frozen=True)
class RecoveryResumeResult:
    state: str
    failure_stage: str
    failure_category: str
    preflight_reads: int
    recovery_calls: int
    secret_probe_calls: int
    protected_source_reads: int
    secret_write_calls: int
    app_setting_write_calls: int
    rollback_calls: int
    resources_closed: bool
    secret_existed: bool
    data_plane_probe_calls: int = 0
    data_plane_status_code: int = 0
    data_plane_region_header_present: bool = False
    data_plane_request_id_header_present: bool = False
    safe_checkpoint_preserved: bool = False
    broad_lists: int = 0
    values_exposed: bool = False


async def recover_and_resume_once(
    *,
    runner=None,
    health=None,
    probe=None,
    source_builder=None,
    sink=None,
    local_state_guard: Callable[[], bool] = lambda: True,
    propagation_seconds: int = RBAC_PROPAGATION_SECONDS,
    probe_retry_seconds: int = SECRET_PROBE_RETRY_SECONDS,
    max_secret_probes: int = MAX_SECRET_PROBES,
    data_plane_probe=None,
    data_plane_probe_interval_seconds: int = DATA_PLANE_PROBE_INTERVAL_SECONDS,
    max_data_plane_probes: int = MAX_DATA_PLANE_PROBES,
    secret_absence_preverified: bool = False,
    secret_presence_preverified: bool = False,
    active_checkpoint_only: bool = False,
    preserve_active_vault: bool = False,
    active_checkpoint_preverified: bool = False,
    skip_data_plane_readiness: bool = False,
) -> RecoveryResumeResult:
    if secret_absence_preverified and secret_presence_preverified:
        raise ValueError("r1_recovery_secret_checkpoint_conflict")
    if type(max_secret_probes) is not int or not 1 <= max_secret_probes <= MAX_SECRET_PROBES:
        raise ValueError("r1_recovery_secret_probe_budget_invalid")
    if type(max_data_plane_probes) is not int or not 1 <= max_data_plane_probes <= MAX_DATA_PLANE_PROBES:
        raise ValueError("r1_recovery_data_plane_probe_budget_invalid")
    uses_real_protected_runtime = probe is None or sink is None
    if uses_real_protected_runtime:
        _validate_real_runtime_dependencies()
    selected_runner = runner or ExactAzureCliCommandRunner()
    selected_health = health or ExactDormantHealthReader()
    selected_probe = probe or ExactSecretExistenceProbe()
    selected_data_plane_probe = data_plane_probe or ExactVaultDataPlaneReadinessProbe()
    selected_sink = sink or AzureKeyVaultExactSecretSink()
    build_source = source_builder or build_real_windows_credential_backend
    source = None
    buffers: dict[str, bytearray] = {}
    payload_owner = None
    payload = bytearray()
    stage = "preflight"
    category = "none"
    preflight_reads = recovery_calls = probe_calls = data_plane_calls = source_reads = writes = setting_writes = rollback_calls = 0
    recovered = identity = reader_role = writer_role = setting = False
    vault_active = False
    writer_removed = False
    safe_checkpoint_preserved = False
    secret_existed = False
    operation_ok = False
    resources_closed = True
    principal_id = operator_id = ""
    try:
        import json, uuid
        if active_checkpoint_preverified:
            if local_state_guard() is not True:
                raise RuntimeError("r1_recovery_preflight_drift")
            operator_id = _successful(
                await selected_runner.run_exact_once(OPERATOR_SHOW)
            ); preflight_reads += 1
            uuid.UUID(operator_id)
            active_exact = True
            deleted_exact = False
        else:
            account = _successful(await selected_runner.run_exact_once(ACCOUNT_SHOW)); preflight_reads += 1
            active = await selected_runner.run_exact_once(VAULT_SHOW); preflight_reads += 1
            deleted = await selected_runner.run_exact_once(VAULT_DELETED_SHOW); preflight_reads += 1
            web = _successful(await selected_runner.run_exact_once(WEB_APP_SHOW)); preflight_reads += 1
            operator_id = _successful(await selected_runner.run_exact_once(OPERATOR_SHOW)); preflight_reads += 1
            web_state = json.loads(web)
            active_exact = active.return_code == 0 and active.stdout == VAULT_ID
            deleted_exact = deleted.return_code == 0 and deleted.stdout == VAULT_ID
            active_absent = active.return_code != 0 and not active.stdout
            deleted_absent = deleted.return_code != 0 and not deleted.stdout
            if (
                account != SUBSCRIPTION_ID
                or not (
                    (active_exact and deleted_absent)
                    or (active_absent and deleted_exact)
                )
                or web_state != [WEB_APP_ID, "Running", "app,linux", "PYTHON|3.12", None]
                or local_state_guard() is not True
            ):
                raise RuntimeError("r1_recovery_preflight_drift")
        uuid.UUID(operator_id)

        vault_active = active_exact
        if active_checkpoint_only and not active_exact:
            raise RuntimeError("r1_recovery_active_checkpoint_required_drift")
        if deleted_exact:
            stage = "recover_vault"; recovery_calls = 1; recovered = True
            if _successful(await selected_runner.run_exact_once(VAULT_RECOVER)) != VAULT_ID:
                raise RuntimeError("r1_recovery_vault_drift")
            _successful(await selected_runner.run_exact_once(VAULT_WAIT_RECOVERED))
            vault_active = True
        if not active_checkpoint_preverified:
            stage = "recover_postread"
            if _successful(await selected_runner.run_exact_once(VAULT_ACTIVE_ARM_SHOW)) != VAULT_ID:
                raise RuntimeError("r1_recovery_vault_postread_drift")

        stage = "data_plane_readiness"
        ready = skip_data_plane_readiness
        if not skip_data_plane_readiness:
            for data_plane_number in range(1, max_data_plane_probes + 1):
                data_plane_calls = data_plane_number
                if await selected_data_plane_probe.ready_once():
                    ready = True
                    break
                if data_plane_number < max_data_plane_probes and data_plane_probe_interval_seconds:
                    await asyncio.sleep(data_plane_probe_interval_seconds)
        if not ready:
            raise RuntimeError("r1_recovery_data_plane_not_ready_transport")

        stage = "writer_role"; writer_role = True
        writer = _role_create(
            principal_id=operator_id, role_id=WRITER_ROLE_DEFINITION_ID,
            assignment_id=WRITER_ROLE_ASSIGNMENT_ID, principal_type="User",
        )
        if _successful(await selected_runner.run_exact_once(writer)) != WRITER_ROLE_ASSIGNMENT_ID:
            raise RuntimeError("r1_recovery_writer_role_drift")
        stage = "writer_rbac_propagation"
        if propagation_seconds:
            await asyncio.sleep(propagation_seconds)

        if secret_presence_preverified:
            secret_existed = True
        elif secret_absence_preverified:
            secret_existed = False
        else:
            stage = "secret_probe"
            for probe_number in range(1, max_secret_probes + 1):
                probe_calls = probe_number
                try:
                    secret_existed = await selected_probe.exists_once()
                    break
                except RuntimeError as error:
                    recoverable = str(error).endswith((
                        "_authorization", "_not_found", "_transport", "_unknown"
                    ))
                    if not recoverable or probe_number >= max_secret_probes:
                        raise
                    if probe_retry_seconds:
                        await asyncio.sleep(probe_retry_seconds)
        if not secret_existed:
            stage = "protected_source"
            source = WindowsCredentialProtectedValueSource(backend=build_source())
            await source.open()
            for name in PROTECTED_SETTING_NAMES:
                buffers[name] = await source.read(name); source_reads += 1
                if not buffers[name]:
                    raise RuntimeError("r1_recovery_protected_value_invalid")
            payload_owner = materialize_key_vault_secret_payload(buffers)
            payload = payload_owner.take_once()
            stage = "secret_write"; writes = 1
            await selected_sink.set_exact_secret_once(payload)

        stage = "writer_cleanup"
        _successful(await selected_runner.run_exact_once(WRITER_ROLE_DELETE))
        writer_removed = True
        stage = "identity"; identity = True
        principal_id = _successful(await selected_runner.run_exact_once(IDENTITY_ENABLE))
        uuid.UUID(principal_id)
        stage = "reader_role"; reader_role = True
        reader = _role_create(
            principal_id=principal_id, role_id=ROLE_DEFINITION_ID,
            assignment_id=ROLE_ASSIGNMENT_ID, principal_type="ServicePrincipal",
        )
        if _successful(await selected_runner.run_exact_once(reader)) != ROLE_ASSIGNMENT_ID:
            raise RuntimeError("r1_recovery_reader_role_drift")
        stage = "app_setting"; setting = True; setting_writes = 1
        _successful(await selected_runner.run_exact_once(APP_SETTING_SET))
        stage = "health"
        healthy = await selected_health.read_exact_once() is True
        if not healthy:
            await asyncio.sleep(15)
            healthy = await selected_health.read_exact_once() is True
        if not healthy:
            raise RuntimeError("r1_recovery_health_drift")
        operation_ok = True
        stage = "complete"
    except BaseException as error:
        code = str(error)
        category = next((item for item in (
            "authentication", "authorization", "not_found", "transport", "unknown"
        ) if code.endswith("_" + item)), "drift" if "drift" in code else "invalid_evidence")
        safe_checkpoint_preserved = (
            stage == "data_plane_readiness" and category == "transport"
        ) or (
            stage == "secret_probe"
            and category in {"authentication", "authorization", "not_found", "transport", "unknown"}
        )
    finally:
        _zeroize(payload)
        if payload_owner is not None:
            payload_owner.close()
        _zeroize_mapping(buffers)
        for resource in (source, selected_sink, selected_probe, selected_data_plane_probe):
            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                except BaseException:
                    resources_closed = False

    if not operation_ok:
        actions = (
            (setting, APP_SETTING_DELETE),
            (writer_role and not writer_removed, WRITER_ROLE_DELETE),
            (reader_role, ROLE_DELETE),
            (identity, IDENTITY_DISABLE),
            (
                vault_active
                and not safe_checkpoint_preserved
                and not preserve_active_vault,
                VAULT_DELETE,
            ),
        )
        for required, command in actions:
            if required:
                rollback_calls += 1
                try:
                    _successful(await selected_runner.run_exact_once(command))
                except BaseException:
                    resources_closed = False
    try:
        await selected_runner.close()
        await selected_health.close()
    except BaseException:
        resources_closed = False
    state = (
        "RECOVERED-DORMANT-VERIFIED" if operation_ok and resources_closed
        else "WAITING-DATA-PLANE-SAFE" if safe_checkpoint_preserved and stage == "data_plane_readiness" and resources_closed
        else "ATTENTION-REQUIRED-AUTHENTICATION-SAFE" if safe_checkpoint_preserved and category == "authentication" and resources_closed
        else "WAITING-SECRET-ACCESS-SAFE" if safe_checkpoint_preserved and resources_closed
        else "FAILED-RESTORED" if not operation_ok and resources_closed
        else "NO-GO-REMAINDER"
    )
    return RecoveryResumeResult(
        state=state, failure_stage="none" if operation_ok else stage,
        failure_category="none" if operation_ok else category,
        preflight_reads=preflight_reads, recovery_calls=recovery_calls,
        secret_probe_calls=probe_calls, protected_source_reads=source_reads,
        secret_write_calls=writes, app_setting_write_calls=setting_writes,
        rollback_calls=rollback_calls, resources_closed=resources_closed,
        secret_existed=secret_existed,
        data_plane_probe_calls=data_plane_calls,
        data_plane_status_code=getattr(selected_data_plane_probe, "last_status_code", 0),
        data_plane_region_header_present=getattr(selected_data_plane_probe, "region_header_present", False),
        data_plane_request_id_header_present=getattr(selected_data_plane_probe, "request_id_header_present", False),
        safe_checkpoint_preserved=safe_checkpoint_preserved,
    )


__all__ = [
    "ExactBearerSecretExistenceProbe", "ExactBearerSecretSink",
    "ExactSecretExistenceProbe",
    "ExactVaultDataPlaneReadinessProbe",
    "MAX_DATA_PLANE_PROBES", "MAX_SECRET_PROBES", "RecoveryResumeResult",
    "recover_and_resume_once",
]
