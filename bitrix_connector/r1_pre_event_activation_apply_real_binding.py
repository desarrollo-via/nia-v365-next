"""Dormant Azure CLI binding for the exact three-switch R1 activation owner."""

from __future__ import annotations

import asyncio
from pathlib import Path
import os
import shutil
from typing import Protocol

import httpx

from .r1_key_vault_linux_provisioning_owner import (
    RESOURCE_GROUP,
    SUBSCRIPTION_ID,
    WEB_APP_NAME,
)
from .r1_key_vault_linux_provisioning_real_binding import HEALTH_BASE_URL
from .r1_pre_event_activation_apply_owner import (
    ACTIVATION_VALUES,
    R1PreEventActivationApplyOwner,
)
from .r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES,
    SWITCH_ORDER,
)


AZURE_CLI = "az"
COMMAND_TIMEOUT_SECONDS = 120
MAX_COMMAND_OUTPUT_BYTES = 4096
MAX_HTTP_BODY_BYTES = 4096

ACTIVATION_SET = (
    AZURE_CLI, "webapp", "config", "appsettings", "set",
    "--resource-group", RESOURCE_GROUP,
    "--name", WEB_APP_NAME,
    "--subscription", SUBSCRIPTION_ID,
    "--settings", *(f"{name}={value}" for name, value in ACTIVATION_VALUES),
    "--output", "none",
)
WEB_APP_RESTART = (
    AZURE_CLI, "webapp", "restart",
    "--resource-group", RESOURCE_GROUP,
    "--name", WEB_APP_NAME,
    "--subscription", SUBSCRIPTION_ID,
    "--output", "none",
)


def _restore_commands(rollback_plan: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    if type(rollback_plan) is not tuple or len(rollback_plan) != len(SWITCH_ORDER):
        raise ValueError("r1_activation_rollback_plan_invalid")
    values: list[str] = []
    absent: list[str] = []
    for name, item in zip(SWITCH_ORDER, rollback_plan, strict=True):
        value_prefix = f"restore-value:{name}="
        absence = f"restore-absence:{name}"
        if item == absence:
            absent.append(name)
        elif type(item) is str and item.startswith(value_prefix):
            value = item.removeprefix(value_prefix)
            if value != EXPECTED_BASELINE_VALUES[name]:
                raise ValueError("r1_activation_rollback_value_invalid")
            values.append(f"{name}={value}")
        else:
            raise ValueError("r1_activation_rollback_plan_invalid")
    commands: list[tuple[str, ...]] = []
    if values:
        commands.append((
            AZURE_CLI, "webapp", "config", "appsettings", "set",
            "--resource-group", RESOURCE_GROUP,
            "--name", WEB_APP_NAME,
            "--subscription", SUBSCRIPTION_ID,
            "--settings", *values,
            "--output", "none",
        ))
    if absent:
        commands.append((
            AZURE_CLI, "webapp", "config", "appsettings", "delete",
            "--resource-group", RESOURCE_GROUP,
            "--name", WEB_APP_NAME,
            "--subscription", SUBSCRIPTION_ID,
            "--setting-names", *absent,
            "--output", "none",
        ))
    if not commands:
        raise ValueError("r1_activation_rollback_plan_invalid")
    return tuple(commands)


def _is_allowlisted_activation_command(command: tuple[str, ...]) -> bool:
    if command in {ACTIVATION_SET, WEB_APP_RESTART}:
        return True
    try:
        if command != _restore_commands(tuple(
            f"restore-value:{name}={EXPECTED_BASELINE_VALUES[name]}"
            for name in SWITCH_ORDER
        ))[0]:
            # Mixed baselines are validated structurally below.
            pass
    except ValueError:
        return False
    if type(command) is not tuple or not command or command[0] != AZURE_CLI:
        return False
    allowed_values = {
        f"{name}={EXPECTED_BASELINE_VALUES[name]}" for name in SWITCH_ORDER
    }
    if command[:5] == (AZURE_CLI, "webapp", "config", "appsettings", "set"):
        try:
            marker = command.index("--settings")
            output = command.index("--output")
        except ValueError:
            return False
        values = command[marker + 1:output]
        fixed = (
            command[5:marker] == (
                "--resource-group", RESOURCE_GROUP,
                "--name", WEB_APP_NAME,
                "--subscription", SUBSCRIPTION_ID,
            )
            and command[output:] == ("--output", "none")
        )
        return bool(fixed and values and len(set(values)) == len(values) and set(values) <= allowed_values)
    if command[:5] == (AZURE_CLI, "webapp", "config", "appsettings", "delete"):
        try:
            marker = command.index("--setting-names")
            output = command.index("--output")
        except ValueError:
            return False
        names = command[marker + 1:output]
        fixed = (
            command[5:marker] == (
                "--resource-group", RESOURCE_GROUP,
                "--name", WEB_APP_NAME,
                "--subscription", SUBSCRIPTION_ID,
            )
            and command[output:] == ("--output", "none")
        )
        return bool(fixed and names and len(set(names)) == len(names) and set(names) <= set(SWITCH_ORDER))
    return False


class ActivationCommandRunner(Protocol):
    async def run_exact_once(self, command: tuple[str, ...]) -> int: ...
    async def close(self) -> None: ...


class ActivationStateVerifier(Protocol):
    async def verify_active_once(self) -> bool: ...
    async def verify_dormant_once(self) -> bool: ...
    async def close(self) -> None: ...


class ExactAnonymousR1ActivationVerifier:
    """Verifies active/dormant mounting without reading a protected token."""

    __slots__ = ("_client_factory", "_phase")

    def __init__(self, *, client_factory=httpx.AsyncClient) -> None:
        if not callable(client_factory):
            raise TypeError("r1_activation_http_client_factory_invalid")
        self._client_factory = client_factory
        self._phase = 0

    async def _read_once(self, *, active: bool) -> bool:
        expected_phase = 0 if active else 1
        if self._phase != expected_phase:
            raise RuntimeError("r1_activation_http_verification_order_invalid")
        self._phase += 1
        client = self._client_factory(
            timeout=30, follow_redirects=False, trust_env=False
        )
        try:
            nia = await client.get(f"{HEALTH_BASE_URL}/health")
            connector = await client.get(
                f"{HEALTH_BASE_URL}/bitrix-connector/health"
            )
            status = await client.get(
                f"{HEALTH_BASE_URL}/bitrix-connector/internal/r1-event/status"
            )
        finally:
            await client.aclose()
        if any(
            len(response.content) > MAX_HTTP_BODY_BYTES
            for response in (nia, connector, status)
        ):
            return False
        if nia.status_code != 200 or connector.status_code != 200:
            return False
        try:
            nia_payload = nia.json()
            connector_payload = connector.json()
            status_payload = status.json()
        except ValueError:
            return False
        health_ok = (
            nia_payload.get("status") == "ok"
            and connector_payload.get("status") == "ok"
            and connector_payload.get("version") == "v0.267"
            and connector_payload.get("requested_mode") == "off"
            and connector_payload.get("effective_mode") == "off"
            and connector_payload.get("activation_locked") is True
            and connector_payload.get("external_calls_enabled") is False
            and connector_payload.get("runtime_state") == "inert"
            and connector_payload.get("r0_bridge", {}).get("mounted") is False
        )
        if active:
            route_ok = (
                status.status_code == 401
                and status_payload == {"code": "review_unauthorized"}
            )
        else:
            route_ok = status.status_code == 404
        return bool(health_ok and route_ok)

    async def verify_active_once(self) -> bool:
        return await self._read_once(active=True)

    async def verify_dormant_once(self) -> bool:
        return await self._read_once(active=False)

    async def close(self) -> None:
        self._client_factory = None

    def __repr__(self) -> str:
        return "ExactAnonymousR1ActivationVerifier(<redacted>)"


class ExactActivationAzureCliRunner:
    """Runs one allowlisted argv without a shell and discards all output."""

    __slots__ = ("_closed", "_prefix", "_used")

    def __init__(self) -> None:
        executable = shutil.which(AZURE_CLI)
        if not executable:
            raise RuntimeError("r1_activation_azure_cli_unavailable")
        path = Path(executable).resolve()
        if os.name == "nt" and path.suffix.casefold() == ".cmd":
            python = path.parent.parent / "python.exe"
            if not python.is_file():
                raise RuntimeError("r1_activation_azure_cli_python_unavailable")
            self._prefix = (str(python), "-IBm", "azure.cli")
        elif path.suffix.casefold() != ".cmd":
            self._prefix = (str(path),)
        else:
            raise RuntimeError("r1_activation_azure_cli_wrapper_unsupported")
        self._used = False
        self._closed = False

    async def run_exact_once(self, command: tuple[str, ...]) -> int:
        if self._closed or self._used or not _is_allowlisted_activation_command(command):
            self._used = True
            raise RuntimeError("r1_activation_command_rejected")
        self._used = True
        process = await asyncio.create_subprocess_exec(
            *self._prefix, *command[1:],
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=MAX_COMMAND_OUTPUT_BYTES + 1,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=COMMAND_TIMEOUT_SECONDS
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise RuntimeError("r1_activation_command_timeout") from None
        if len(stdout) > MAX_COMMAND_OUTPUT_BYTES or len(stderr) > MAX_COMMAND_OUTPUT_BYTES:
            raise RuntimeError("r1_activation_command_output_oversized")
        stdout = stderr = b""
        return int(process.returncode)

    async def close(self) -> None:
        self._closed = True


class R1ActivationAzureCliApplyControl:
    """Concrete apply/restart/restore mapping with an injected exact verifier."""

    __slots__ = ("_closed", "_calls", "_runner_factory", "_verifier")

    def __init__(self, *, runner_factory, verifier: ActivationStateVerifier) -> None:
        if not callable(runner_factory) or any(
            not callable(getattr(verifier, name, None))
            for name in ("verify_active_once", "verify_dormant_once", "close")
        ):
            raise TypeError("r1_activation_binding_dependency_invalid")
        self._runner_factory = runner_factory
        self._verifier: ActivationStateVerifier | None = verifier
        self._calls: set[str] = set()
        self._closed = False

    def _claim(self, name: str) -> None:
        if self._closed or name in self._calls:
            raise RuntimeError("r1_activation_binding_operation_reused")
        self._calls.add(name)

    async def _run(self, command: tuple[str, ...]) -> None:
        runner = self._runner_factory()
        closed = True
        try:
            code = await runner.run_exact_once(command)
            if code != 0:
                raise RuntimeError("r1_activation_command_failed")
        finally:
            try:
                await runner.close()
            except BaseException:
                closed = False
        if not closed:
            raise RuntimeError("r1_activation_runner_close_failed")

    async def apply_exact_switches_once(self, values) -> None:
        self._claim("apply")
        if values != ACTIVATION_VALUES:
            raise ValueError("r1_activation_values_invalid")
        await self._run(ACTIVATION_SET)

    async def restart_after_apply_once(self) -> None:
        self._claim("restart_apply")
        await self._run(WEB_APP_RESTART)

    async def verify_active_once(self) -> bool:
        self._claim("verify_active")
        return bool(self._verifier and await self._verifier.verify_active_once())

    async def restore_exact_switches_once(self, rollback_plan) -> None:
        self._claim("restore")
        for command in _restore_commands(rollback_plan):
            await self._run(command)

    async def restart_after_restore_once(self) -> None:
        self._claim("restart_restore")
        await self._run(WEB_APP_RESTART)

    async def verify_dormant_once(self) -> bool:
        self._claim("verify_dormant")
        return bool(self._verifier and await self._verifier.verify_dormant_once())

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        verifier, self._verifier = self._verifier, None
        self._runner_factory = None
        if verifier is not None:
            await verifier.close()

    def __repr__(self) -> str:
        return "R1ActivationAzureCliApplyControl(<redacted>)"


def build_dormant_real_activation_apply_owner(
    *, verifier: ActivationStateVerifier,
    runner_factory=ExactActivationAzureCliRunner,
) -> R1PreEventActivationApplyOwner:
    """Construction is inert; effects begin only when the owner executes."""

    return R1PreEventActivationApplyOwner(
        control=R1ActivationAzureCliApplyControl(
            runner_factory=runner_factory,
            verifier=verifier,
        )
    )


__all__ = [
    "ACTIVATION_SET", "ActivationStateVerifier", "ExactActivationAzureCliRunner",
    "ExactAnonymousR1ActivationVerifier",
    "R1ActivationAzureCliApplyControl", "WEB_APP_RESTART",
    "_is_allowlisted_activation_command", "_restore_commands",
    "build_dormant_real_activation_apply_owner",
]
