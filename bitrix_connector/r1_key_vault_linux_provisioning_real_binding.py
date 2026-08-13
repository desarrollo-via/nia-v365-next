"""Dormant concrete binding for the fixed R1 Key Vault provisioning owner."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
import shutil
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

import httpx

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    WindowsCredentialProtectedValueSource,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .r1_key_vault_exact_secret_backend import (
    KEY_VAULT_SECRET_NAME,
    MAX_KEY_VAULT_ENCODED_SECRET_BYTES,
)
from .r1_key_vault_linux_provisioning_owner import (
    APP_SETTING_NAME,
    AzureProvisioningPreflightEvidence,
    RESOURCE_GROUP,
    ROLE_ASSIGNMENT_ID,
    ROLE_DEFINITION_ID,
    R1KeyVaultLinuxProvisioningOwner,
    SUBSCRIPTION_ID,
    VAULT_ID,
    VAULT_NAME,
    VAULT_URL,
    WEB_APP_ID,
    WEB_APP_NAME,
    WRITER_ROLE_ASSIGNMENT_ID,
    WRITER_ROLE_DEFINITION_ID,
)


AZURE_CLI = "az"
AZURE_LOCATION = "canadacentral"
KEY_VAULT_PROVIDER_NAMESPACE = "Microsoft.KeyVault"
MAX_COMMAND_OUTPUT_BYTES = 8192
COMMAND_TIMEOUT_SECONDS = 60
PROVIDER_REGISTRATION_TIMEOUT_SECONDS = 600
HEALTH_BASE_URL = (
    "https://nia-v365-next-api-ekd4fza7e0fzevfd."
    "canadacentral-01.azurewebsites.net"
)
ROLE_ASSIGNMENT_RESOURCE_ID = (
    f"{VAULT_ID}/providers/Microsoft.Authorization/roleAssignments/"
    f"{ROLE_ASSIGNMENT_ID}"
)
WRITER_ROLE_ASSIGNMENT_RESOURCE_ID = (
    f"{VAULT_ID}/providers/Microsoft.Authorization/roleAssignments/"
    f"{WRITER_ROLE_ASSIGNMENT_ID}"
)


ACCOUNT_SHOW = (
    AZURE_CLI, "rest", "--method", "get", "--url",
    f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
    "?api-version=2022-12-01",
    "--query", "subscriptionId", "--output", "tsv"
)
WEB_APP_SHOW = (
    AZURE_CLI, "webapp", "show", "--resource-group", RESOURCE_GROUP,
    "--name", WEB_APP_NAME, "--subscription", SUBSCRIPTION_ID, "--query",
    "[id,state,kind,siteConfig.linuxFxVersion,identity.principalId]",
    "--output", "json",
)
VAULT_SHOW = (
    AZURE_CLI, "keyvault", "show", "--resource-group", RESOURCE_GROUP,
    "--name", VAULT_NAME, "--subscription", SUBSCRIPTION_ID,
    "--query", "id", "--output", "tsv",
)
VAULT_ACTIVE_ARM_SHOW = (
    AZURE_CLI, "rest", "--method", "get", "--url",
    f"https://management.azure.com{VAULT_ID}?api-version=2023-07-01",
    "--query", "id", "--output", "tsv",
)
VAULT_DELETED_SHOW = (
    AZURE_CLI, "rest", "--method", "get", "--url",
    f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}/providers/"
    f"Microsoft.KeyVault/locations/{AZURE_LOCATION}/deletedVaults/{VAULT_NAME}"
    "?api-version=2023-07-01",
    "--query", "properties.vaultId", "--output", "tsv",
)
VAULT_NAME_CHECK = (
    AZURE_CLI, "keyvault", "check-name", "--name", VAULT_NAME,
    "--subscription", SUBSCRIPTION_ID, "--query", "nameAvailable",
    "--output", "tsv",
)
OPERATOR_SHOW = (
    AZURE_CLI, "ad", "signed-in-user", "show",
    "--query", "id", "--output", "tsv",
)
VAULT_CREATE = (
    AZURE_CLI, "keyvault", "create", "--resource-group", RESOURCE_GROUP,
    "--name", VAULT_NAME, "--subscription", SUBSCRIPTION_ID,
    "--location", AZURE_LOCATION,
    "--enable-rbac-authorization", "true", "--retention-days", "7",
    "--query", "id", "--output", "tsv",
)
IDENTITY_ENABLE = (
    AZURE_CLI, "webapp", "identity", "assign", "--resource-group",
    RESOURCE_GROUP, "--name", WEB_APP_NAME, "--subscription",
    SUBSCRIPTION_ID, "--query", "principalId", "--output", "tsv",
)
WRITER_ROLE_DELETE = (
    AZURE_CLI, "role", "assignment", "delete", "--ids",
    WRITER_ROLE_ASSIGNMENT_RESOURCE_ID, "--subscription", SUBSCRIPTION_ID,
    "--output", "none",
)
APP_SETTING_SET = (
    AZURE_CLI, "webapp", "config", "appsettings", "set",
    "--resource-group", RESOURCE_GROUP, "--name", WEB_APP_NAME,
    "--subscription", SUBSCRIPTION_ID, "--settings",
    f"{APP_SETTING_NAME}={VAULT_URL}", "--output", "none",
)
APP_SETTING_DELETE = (
    AZURE_CLI, "webapp", "config", "appsettings", "delete",
    "--resource-group", RESOURCE_GROUP, "--name", WEB_APP_NAME,
    "--subscription", SUBSCRIPTION_ID, "--setting-names", APP_SETTING_NAME,
    "--output", "none",
)
ROLE_DELETE = (
    AZURE_CLI, "role", "assignment", "delete", "--ids",
    ROLE_ASSIGNMENT_RESOURCE_ID, "--subscription", SUBSCRIPTION_ID,
    "--output", "none",
)
IDENTITY_DISABLE = (
    AZURE_CLI, "webapp", "identity", "remove", "--resource-group",
    RESOURCE_GROUP, "--name", WEB_APP_NAME, "--identities", "[system]",
    "--subscription", SUBSCRIPTION_ID, "--output", "none",
)
VAULT_DELETE = (
    AZURE_CLI, "keyvault", "delete", "--resource-group", RESOURCE_GROUP,
    "--name", VAULT_NAME, "--subscription", SUBSCRIPTION_ID,
    "--output", "none",
)
VAULT_RECOVER = (
    AZURE_CLI, "keyvault", "recover", "--name", VAULT_NAME,
    "--location", AZURE_LOCATION, "--subscription", SUBSCRIPTION_ID,
    "--query", "id", "--output", "tsv",
)
VAULT_WAIT_RECOVERED = (
    AZURE_CLI, "keyvault", "wait", "--name", VAULT_NAME,
    "--resource-group", RESOURCE_GROUP, "--subscription", SUBSCRIPTION_ID,
    "--created", "--interval", "5", "--timeout", "120", "--output", "none",
)
VAULT_CREATE_ACTIVITY = (
    AZURE_CLI, "monitor", "activity-log", "list",
    "--resource-id", VAULT_ID,
    "--start-time", "2026-08-12T15:35:13Z",
    "--end-time", "2026-08-12T15:39:13Z",
    "--subscription", SUBSCRIPTION_ID,
    "--max-events", "5",
    "--select", "eventTimestamp", "operationName", "status", "subStatus",
    "--output", "json",
)
VAULT_CREATE_CAUSE_ACTIVITY = (
    AZURE_CLI, "monitor", "activity-log", "list",
    "--resource-id", VAULT_ID,
    "--start-time", "2026-08-12T15:35:13Z",
    "--end-time", "2026-08-12T15:39:13Z",
    "--subscription", SUBSCRIPTION_ID,
    "--max-events", "5",
    "--select", "operationName", "status", "properties",
    "--query",
    "[?operationName.value=='Microsoft.KeyVault/vaults/write' && "
    "status.value=='Failed'] | [0].properties.statusMessage",
    "--output", "json",
)
KEY_VAULT_PROVIDER_SHOW = (
    AZURE_CLI, "provider", "show",
    "--namespace", KEY_VAULT_PROVIDER_NAMESPACE,
    "--subscription", SUBSCRIPTION_ID,
    "--query", "registrationState", "--output", "tsv",
)
KEY_VAULT_PROVIDER_REGISTER = (
    AZURE_CLI, "provider", "register",
    "--namespace", KEY_VAULT_PROVIDER_NAMESPACE,
    "--subscription", SUBSCRIPTION_ID,
    "--wait", "--query", "registrationState", "--output", "tsv",
)


def _role_definition_show(role_id: str) -> tuple[str, ...]:
    return (
        AZURE_CLI, "role", "definition", "list", "--name", role_id,
        "--subscription", SUBSCRIPTION_ID, "--query", "[0].name",
        "--output", "tsv",
    )


def _role_create(
    *, principal_id: str, role_id: str, assignment_id: str, principal_type: str
) -> tuple[str, ...]:
    uuid.UUID(principal_id)
    uuid.UUID(role_id)
    uuid.UUID(assignment_id)
    if principal_type not in {"ServicePrincipal", "User"}:
        raise ValueError("r1_kv_binding_principal_type_invalid")
    return (
        AZURE_CLI, "role", "assignment", "create", "--assignee-object-id",
        principal_id, "--assignee-principal-type", principal_type, "--role",
        role_id, "--scope", VAULT_ID, "--name", assignment_id,
        "--subscription", SUBSCRIPTION_ID, "--query", "name", "--output",
        "tsv",
    )


def _is_allowlisted_command(command: tuple[str, ...]) -> bool:
    static = {
        ACCOUNT_SHOW, WEB_APP_SHOW, VAULT_SHOW, VAULT_ACTIVE_ARM_SHOW,
        VAULT_DELETED_SHOW,
        VAULT_NAME_CHECK,
        OPERATOR_SHOW, VAULT_CREATE, IDENTITY_ENABLE, WRITER_ROLE_DELETE,
        APP_SETTING_SET, APP_SETTING_DELETE, ROLE_DELETE, IDENTITY_DISABLE,
        VAULT_DELETE, VAULT_RECOVER, VAULT_WAIT_RECOVERED,
        VAULT_CREATE_ACTIVITY, VAULT_CREATE_CAUSE_ACTIVITY,
        KEY_VAULT_PROVIDER_SHOW, KEY_VAULT_PROVIDER_REGISTER,
        _role_definition_show(ROLE_DEFINITION_ID),
        _role_definition_show(WRITER_ROLE_DEFINITION_ID),
    }
    if command in static:
        return True
    if len(command) != 20 or command[:4] != (
        AZURE_CLI, "role", "assignment", "create"
    ):
        return False
    try:
        return command == _role_create(
            principal_id=command[5],
            principal_type=command[7],
            role_id=command[9],
            assignment_id=command[13],
        )
    except (ValueError, TypeError, IndexError):
        return False


@dataclass(frozen=True)
class SanitizedCommandResult:
    return_code: int
    stdout: str = ""
    failure_category: str = "none"


def _classify_stderr(stderr: bytes) -> str:
    try:
        lowered = stderr.decode("utf-8", errors="replace").casefold()
    finally:
        stderr = b""
    if any(marker in lowered for marker in ("aadsts", "az login", "credential", "token")):
        return "authentication"
    if any(marker in lowered for marker in ("authorizationfailed", "forbidden", "permission")):
        return "authorization"
    if any(marker in lowered for marker in ("resourcenotfound", "could not be found", "not found")):
        return "not_found"
    if any(marker in lowered for marker in ("connection", "dns", "timed out", "timeout")):
        return "transport"
    return "unknown"


class CommandRunner(Protocol):
    async def run_exact_once(
        self, command: tuple[str, ...]
    ) -> SanitizedCommandResult: ...

    async def close(self) -> None: ...


class ExactAzureCliCommandRunner:
    """Executes one allowlisted argv per exact command, never through a shell."""

    __slots__ = ("_closed", "_prefix", "_used")

    def __init__(self) -> None:
        self._used: set[tuple[str, ...]] = set()
        self._closed = False
        executable = shutil.which(AZURE_CLI)
        if not executable:
            raise RuntimeError("r1_kv_binding_azure_cli_unavailable")
        path = Path(executable).resolve()
        if os.name == "nt" and path.suffix.casefold() == ".cmd":
            python = path.parent.parent / "python.exe"
            if not python.is_file():
                raise RuntimeError("r1_kv_binding_azure_cli_python_unavailable")
            self._prefix = (str(python), "-IBm", "azure.cli")
        elif path.suffix.casefold() != ".cmd":
            self._prefix = (str(path),)
        else:
            raise RuntimeError("r1_kv_binding_azure_cli_wrapper_unsupported")

    async def run_exact_once(
        self, command: tuple[str, ...]
    ) -> SanitizedCommandResult:
        if (
            self._closed
            or type(command) is not tuple
            or command in self._used
            or not _is_allowlisted_command(command)
        ):
            raise RuntimeError("r1_kv_binding_command_rejected")
        self._used.add(command)
        executable_command = self._prefix + command[1:]
        process = await asyncio.create_subprocess_exec(
            *executable_command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=MAX_COMMAND_OUTPUT_BYTES + 1,
        )
        try:
            timeout = (
                PROVIDER_REGISTRATION_TIMEOUT_SECONDS
                if command == KEY_VAULT_PROVIDER_REGISTER
                else 150
                if command == VAULT_WAIT_RECOVERED
                else COMMAND_TIMEOUT_SECONDS
            )
            stdout, _stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise RuntimeError("r1_kv_binding_command_timeout") from None
        if len(stdout) > MAX_COMMAND_OUTPUT_BYTES or len(_stderr) > MAX_COMMAND_OUTPUT_BYTES:
            raise RuntimeError("r1_kv_binding_command_output_oversized")
        try:
            text = stdout.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise RuntimeError("r1_kv_binding_command_output_invalid") from error
        failure_category = (
            "none" if process.returncode == 0 else _classify_stderr(_stderr)
        )
        _stderr = b""
        return SanitizedCommandResult(process.returncode, text, failure_category)

    async def close(self) -> None:
        self._closed = True
        self._used.clear()

    def __repr__(self) -> str:
        return "ExactAzureCliCommandRunner(<redacted>)"


class HealthReader(Protocol):
    async def read_exact_once(self) -> bool: ...

    async def close(self) -> None: ...


class ExactDormantHealthReader:
    """Reads only the two public health endpoints, with bounded one-shot pairs."""

    __slots__ = ("_calls", "_client")

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._calls = 0

    async def read_exact_once(self) -> bool:
        if self._calls >= 2:
            raise RuntimeError("r1_kv_binding_health_budget_exhausted")
        self._calls += 1
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30, follow_redirects=False, trust_env=False
            )
        nia = await self._client.get(f"{HEALTH_BASE_URL}/health")
        connector = await self._client.get(
            f"{HEALTH_BASE_URL}/bitrix-connector/health"
        )
        if nia.status_code != 200 or connector.status_code != 200:
            return False
        if len(nia.content) > 4096 or len(connector.content) > 4096:
            return False
        try:
            nia_payload = nia.json()
            payload = connector.json()
        except ValueError:
            return False
        return (
            nia_payload.get("status") == "ok"
            and payload.get("status") == "ok"
            and payload.get("version") == "v0.267"
            and payload.get("requested_mode") == "off"
            and payload.get("effective_mode") == "off"
            and payload.get("activation_locked") is True
            and payload.get("external_calls_enabled") is False
            and payload.get("runtime_state") == "inert"
        )

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


LocalStateGuard = Callable[[], bool]


def _successful(result: SanitizedCommandResult) -> str:
    if type(result) is not SanitizedCommandResult or result.return_code != 0:
        category = (
            result.failure_category
            if type(result) is SanitizedCommandResult
            and result.failure_category in {
                "authentication", "authorization", "not_found", "transport", "unknown"
            }
            else "unknown"
        )
        raise RuntimeError(f"r1_kv_binding_command_failed_{category}")
    return result.stdout


class AzureCliExactProvisioningControl:
    """Concrete command mapping for the owner; every surface is one-shot."""

    __slots__ = (
        "_calls", "_closed", "_health", "_local_state_guard", "_operator_id",
        "_runner", "_setting_absent",
    )

    def __init__(
        self, *, runner: CommandRunner, health: HealthReader,
        local_state_guard: LocalStateGuard, setting_absent: bool
    ) -> None:
        if (
            not callable(getattr(runner, "run_exact_once", None))
            or not callable(getattr(runner, "close", None))
            or not callable(getattr(health, "read_exact_once", None))
            or not callable(getattr(health, "close", None))
            or not callable(local_state_guard)
            or setting_absent is not True
        ):
            raise TypeError("r1_kv_binding_control_dependency_invalid")
        self._runner: CommandRunner | None = runner
        self._health: HealthReader | None = health
        self._local_state_guard: LocalStateGuard | None = local_state_guard
        self._setting_absent = setting_absent
        self._operator_id = ""
        self._calls: set[str] = set()
        self._closed = False

    def _claim(self, name: str) -> None:
        if self._closed or name in self._calls:
            raise RuntimeError("r1_kv_binding_operation_reused")
        self._calls.add(name)

    async def _run(self, command: tuple[str, ...]) -> SanitizedCommandResult:
        if self._runner is None:
            raise RuntimeError("r1_kv_binding_runner_closed")
        return await self._runner.run_exact_once(command)

    async def preflight_exact_once(self) -> AzureProvisioningPreflightEvidence:
        self._claim("preflight")
        account = _successful(await self._run(ACCOUNT_SHOW))
        if account != SUBSCRIPTION_ID:
            raise RuntimeError("r1_kv_binding_preflight_account_drift")
        web_raw = _successful(await self._run(WEB_APP_SHOW))
        try:
            web = json.loads(web_raw)
        except ValueError as error:
            raise RuntimeError("r1_kv_binding_webapp_output_invalid") from error
        if web != [WEB_APP_ID, "Running", "app,linux", "PYTHON|3.12", None]:
            raise RuntimeError("r1_kv_binding_preflight_webapp_drift")
        vault = await self._run(VAULT_SHOW)
        if vault.return_code == 0 or vault.stdout:
            raise RuntimeError("r1_kv_binding_preflight_vault_drift")
        available = _successful(await self._run(VAULT_NAME_CHECK)).lower()
        if available != "true":
            raise RuntimeError("r1_kv_binding_preflight_name_drift")
        reader_role = _successful(
            await self._run(_role_definition_show(ROLE_DEFINITION_ID))
        )
        if reader_role != ROLE_DEFINITION_ID:
            raise RuntimeError("r1_kv_binding_preflight_reader_role_drift")
        writer_role = _successful(
            await self._run(_role_definition_show(WRITER_ROLE_DEFINITION_ID))
        )
        if writer_role != WRITER_ROLE_DEFINITION_ID:
            raise RuntimeError("r1_kv_binding_preflight_writer_role_drift")
        operator_id = _successful(await self._run(OPERATOR_SHOW))
        try:
            uuid.UUID(operator_id)
        except (ValueError, TypeError) as error:
            raise RuntimeError("r1_kv_binding_operator_invalid") from error
        if (
            self._health is None
            or await self._health.read_exact_once() is not True
            or self._local_state_guard is None
            or self._local_state_guard() is not True
        ):
            raise RuntimeError("r1_kv_binding_preflight_drift")
        self._operator_id = operator_id
        return AzureProvisioningPreflightEvidence(
            operator_principal_id=operator_id,
            app_setting_absent=self._setting_absent,
        )

    async def create_exact_vault_once(self) -> str:
        self._claim("create_vault")
        return _successful(await self._run(VAULT_CREATE))

    async def enable_exact_system_identity_once(self) -> str:
        self._claim("enable_identity")
        return _successful(await self._run(IDENTITY_ENABLE))

    async def create_exact_role_assignment_once(self, principal_id: str) -> str:
        self._claim("create_role")
        command = _role_create(
            principal_id=principal_id, role_id=ROLE_DEFINITION_ID,
            assignment_id=ROLE_ASSIGNMENT_ID, principal_type="ServicePrincipal",
        )
        return _successful(await self._run(command))

    async def create_exact_writer_role_assignment_once(self) -> str:
        self._claim("create_writer_role")
        command = _role_create(
            principal_id=self._operator_id,
            role_id=WRITER_ROLE_DEFINITION_ID,
            assignment_id=WRITER_ROLE_ASSIGNMENT_ID,
            principal_type="User",
        )
        return _successful(await self._run(command))

    async def delete_exact_writer_role_assignment_once(self) -> None:
        self._claim("delete_writer_role")
        _successful(await self._run(WRITER_ROLE_DELETE))

    async def set_exact_app_setting_once(self) -> None:
        self._claim("set_setting")
        _successful(await self._run(APP_SETTING_SET))

    async def verify_exact_dormant_health_once(self) -> bool:
        self._claim("health")
        if self._health is None:
            return False
        return await self._health.read_exact_once()

    async def remove_exact_app_setting_once(self) -> None:
        self._claim("rollback_setting")
        _successful(await self._run(APP_SETTING_DELETE))

    async def delete_exact_role_assignment_once(self) -> None:
        self._claim("rollback_role")
        _successful(await self._run(ROLE_DELETE))

    async def disable_exact_system_identity_once(self) -> None:
        self._claim("rollback_identity")
        _successful(await self._run(IDENTITY_DISABLE))

    async def soft_delete_exact_vault_once(self) -> None:
        self._claim("rollback_vault")
        _successful(await self._run(VAULT_DELETE))

    async def verify_exact_vault_rollback_once(self) -> bool:
        self._claim("verify_rollback_vault")
        active = await self._run(VAULT_SHOW)
        deleted = await self._run(VAULT_DELETED_SHOW)
        return (
            active.return_code != 0
            and active.stdout == ""
            and active.failure_category == "not_found"
            and (
                (deleted.return_code == 0 and deleted.stdout == VAULT_ID)
                or (
                    deleted.return_code != 0
                    and deleted.stdout == ""
                    and deleted.failure_category == "not_found"
                )
            )
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        runner, self._runner = self._runner, None
        health, self._health = self._health, None
        self._local_state_guard = None
        failures = 0
        for resource in (runner, health):
            if resource is not None:
                try:
                    await resource.close()
                except BaseException:
                    failures += 1
        if failures:
            raise RuntimeError("r1_kv_binding_control_close_failed")

    def __repr__(self) -> str:
        return "AzureCliExactProvisioningControl(<redacted>)"


class AzureKeyVaultExactSecretSink:
    """Lazy one-shot SDK sink; construction performs no import or network."""

    __slots__ = ("_client", "_credential", "_used")

    def __init__(self) -> None:
        self._client: object | None = None
        self._credential: object | None = None
        self._used = False

    async def set_exact_secret_once(self, payload: bytearray) -> str:
        if (
            self._used or type(payload) is not bytearray or not payload
            or len(payload) > MAX_KEY_VAULT_ENCODED_SECRET_BYTES
        ):
            self._used = True
            raise RuntimeError("r1_kv_binding_secret_payload_invalid")
        self._used = True
        try:
            value = bytes(payload).decode("ascii")
        except UnicodeDecodeError as error:
            raise RuntimeError("r1_kv_binding_secret_payload_invalid") from error
        try:
            from azure.identity.aio import AzureCliCredential
            from azure.keyvault.secrets.aio import SecretClient

            self._credential = AzureCliCredential()
            self._client = SecretClient(
                vault_url=VAULT_URL, credential=self._credential
            )
            response = await self._client.set_secret(KEY_VAULT_SECRET_NAME, value)
            secret_id = getattr(response, "id", None)
            if type(secret_id) is not str or not secret_id.startswith(
                f"{VAULT_URL}secrets/{KEY_VAULT_SECRET_NAME}/"
            ):
                raise RuntimeError("r1_kv_binding_secret_id_invalid")
            return secret_id
        except Exception as error:
            status = getattr(error, "status_code", None)
            name = type(error).__name__.casefold()
            if status == 401 or "authentication" in name or "credentialunavailable" in name:
                category = "authentication"
            elif status == 403 or "forbidden" in name:
                category = "authorization"
            elif status == 404 or "notfound" in name:
                category = "not_found"
            elif status in {408, 429, 500, 502, 503, 504} or "transport" in name or "timeout" in name:
                category = "transport"
            else:
                category = "unknown"
            raise RuntimeError(
                f"r1_kv_binding_secret_write_failed_{category}"
            ) from None
        finally:
            value = ""

    async def close(self) -> None:
        client, self._client = self._client, None
        credential, self._credential = self._credential, None
        failures = 0
        for resource in (client, credential):
            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except BaseException:
                    failures += 1
        if failures:
            raise RuntimeError("r1_kv_binding_secret_sink_close_failed")

    def __repr__(self) -> str:
        return "AzureKeyVaultExactSecretSink(<redacted>)"


def build_dormant_real_provisioning_owner(
    *, local_state_guard: LocalStateGuard,
    runner: CommandRunner | None = None,
    health: HealthReader | None = None,
    source_builder: Callable[[], object] | None = None,
    sink: object | None = None,
) -> R1KeyVaultLinuxProvisioningOwner:
    """Builds the concrete owner without opening any protected/external surface."""

    selected_runner = runner or ExactAzureCliCommandRunner()
    selected_health = health or ExactDormantHealthReader()
    builder = source_builder or build_real_windows_credential_backend
    backend = builder()
    source = WindowsCredentialProtectedValueSource(backend=backend)
    selected_sink = sink or AzureKeyVaultExactSecretSink()
    control = AzureCliExactProvisioningControl(
        runner=selected_runner,
        health=selected_health,
        local_state_guard=local_state_guard,
        setting_absent=True,
    )
    return R1KeyVaultLinuxProvisioningOwner(
        control=control,
        source=source,
        sink=selected_sink,
        real_binding_present=True,
    )


__all__ = [
    "APP_SETTING_DELETE", "APP_SETTING_SET", "AzureCliExactProvisioningControl",
    "AzureKeyVaultExactSecretSink", "ExactAzureCliCommandRunner",
    "ExactDormantHealthReader", "KEY_VAULT_PROVIDER_NAMESPACE",
    "KEY_VAULT_PROVIDER_REGISTER", "KEY_VAULT_PROVIDER_SHOW",
    "PROVIDER_REGISTRATION_TIMEOUT_SECONDS",
    "SanitizedCommandResult", "VAULT_CREATE_ACTIVITY",
    "VAULT_ACTIVE_ARM_SHOW", "VAULT_CREATE_CAUSE_ACTIVITY",
    "VAULT_DELETED_SHOW", "VAULT_RECOVER",
    "VAULT_WAIT_RECOVERED",
    "build_dormant_real_provisioning_owner",
]
