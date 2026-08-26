"""Persistent two-phase host executor for the consumed R1 post-write cut."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal

import httpx
from azure.identity.aio import ManagedIdentityCredential

from .r1_key_vault_exact_secret_backend import KEY_VAULT_SECRET_NAME
from .r1_key_vault_linux_provisioning_owner import (
    SUBSCRIPTION_ID,
    VAULT_ID,
    VAULT_URL,
    WEB_APP_ID,
    WRITER_ROLE_ASSIGNMENT_ID,
)
from .r1_post_write_close_recovery import (
    PostWriteCloseResult,
    verify_consumed_write_checkpoint,
)
from .r1_pre_event_activation_apply_owner import ACTIVATION_VALUES
from .r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES,
    SWITCH_ORDER,
)


ARM_SCOPE = "https://management.azure.com/.default"
VAULT_SCOPE = "https://vault.azure.net/.default"
ARM_ROOT = "https://management.azure.com"
WEB_API = "2023-12-01"
AUTH_API = "2022-04-01"
KV_API = "2023-07-01"
SECRET_API = "7.5"
MAX_ARM_BODY = 262_144
DEFAULT_STATE_PATH = Path(
    "/home/data/nia-next/r1-post-write-close-v1.json"
)
Phase = Literal[
    "CLAIMED", "RESTART-REQUESTED", "VERIFIED", "NO-GO"
]


@dataclass(frozen=True)
class HostCloseState:
    phase: Phase
    session_closed: bool = False
    key_vault_closed: bool = False
    activation_requested: bool = False


class PersistentHostCloseStore:
    """Exact, atomic state file; it stores no token or protected value."""

    __slots__ = ("_path",)

    def __init__(self, *, path: Path = DEFAULT_STATE_PATH) -> None:
        if (
            not isinstance(path, Path)
            or (path != DEFAULT_STATE_PATH and not path.is_absolute())
        ):
            raise TypeError("r1_post_write_host_state_path_invalid")
        self._path = path

    def read(self) -> HostCloseState | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if type(payload) is not dict or set(payload) != {
                "phase", "session_closed", "key_vault_closed",
                "activation_requested",
            }:
                return HostCloseState("NO-GO")
            if (
                payload["phase"] not in {
                    "CLAIMED", "RESTART-REQUESTED", "VERIFIED", "NO-GO"
                }
                or any(
                    type(payload[name]) is not bool
                    for name in (
                        "session_closed", "key_vault_closed",
                        "activation_requested",
                    )
                )
            ):
                return HostCloseState("NO-GO")
            return HostCloseState(**payload)
        except (OSError, TypeError, ValueError):
            return HostCloseState("NO-GO")

    def claim_once(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            HostCloseState("CLAIMED").__dict__,
            separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        try:
            descriptor = os.open(
                self._path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return False
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return True

    def replace(self, state: HostCloseState) -> None:
        temporary = self._path.with_suffix(".tmp")
        payload = json.dumps(
            state.__dict__, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        descriptor = os.open(
            temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self._path)


class ExactManagedIdentityPostWriteControl:
    """Exact ARM/Key Vault closure; bodies and tokens never escape."""

    __slots__ = ("_credential", "_http")

    def __init__(self, *, credential=None, http_client=None) -> None:
        self._credential = credential or ManagedIdentityCredential()
        self._http = http_client or httpx.AsyncClient(
            timeout=30, follow_redirects=False, trust_env=False
        )

    async def _token(self, scope: str) -> str:
        token = await self._credential.get_token(scope)
        value = getattr(token, "token", "")
        if type(value) is not str or not value:
            raise RuntimeError("r1_post_write_host_authentication")
        return value

    async def _arm(self, method: str, suffix: str, *, body=None):
        token = await self._token(ARM_SCOPE)
        try:
            return await self._http.request(
                method,
                f"{ARM_ROOT}{suffix}",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
        finally:
            token = ""

    @staticmethod
    def _bounded_properties(response) -> dict[str, object]:
        if response.status_code != 200 or len(response.content) > MAX_ARM_BODY:
            raise RuntimeError("r1_post_write_appsettings_read_failed")
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError("r1_post_write_appsettings_invalid") from None
        properties = payload.get("properties") if type(payload) is dict else None
        if type(properties) is not dict or any(
            type(name) is not str or type(value) is not str
            for name, value in properties.items()
        ):
            raise RuntimeError("r1_post_write_appsettings_invalid")
        return properties

    async def _secret_exists_without_body_once(self) -> bool:
        token = await self._token(VAULT_SCOPE)
        try:
            async with self._http.stream(
                "GET",
                f"{VAULT_URL}secrets/{KEY_VAULT_SECRET_NAME}",
                params={"api-version": SECRET_API},
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                return response.status_code == 200
        finally:
            token = ""

    async def preflight_once(self) -> bool:
        config = (
            f"{WEB_APP_ID}/config/appsettings/list?api-version={WEB_API}"
        )
        current = self._bounded_properties(await self._arm("POST", config))
        active = dict(ACTIVATION_VALUES)
        switches_known = all(
            current.get(name) in {
                active[name], EXPECTED_BASELINE_VALUES[name]
            }
            for name in SWITCH_ORDER
        )
        current = active = {}
        vault = await self._arm("GET", f"{VAULT_ID}?api-version={KV_API}")
        assignment = (
            f"{VAULT_ID}/providers/Microsoft.Authorization/roleAssignments/"
            f"{WRITER_ROLE_ASSIGNMENT_ID}?api-version={AUTH_API}"
        )
        writer = await self._arm("GET", assignment)
        return bool(
            switches_known
            and vault.status_code == 200
            and writer.status_code in {200, 404}
            and await self._secret_exists_without_body_once()
        )

    async def close_writer_once(self) -> bool:
        assignment = (
            f"{VAULT_ID}/providers/Microsoft.Authorization/roleAssignments/"
            f"{WRITER_ROLE_ASSIGNMENT_ID}?api-version={AUTH_API}"
        )
        deleted = await self._arm("DELETE", assignment)
        if deleted.status_code not in {200, 204, 404}:
            return False
        absent = await self._arm("GET", assignment)
        return absent.status_code == 404

    async def restore_switches_and_restart_once(self) -> None:
        config = (
            f"{WEB_APP_ID}/config/appsettings?api-version={WEB_API}"
        )
        current = self._bounded_properties(
            await self._arm("POST", config.replace("?", "/list?"))
        )
        preserved_count = len(current)
        restored = dict(current)
        for name in SWITCH_ORDER:
            restored[name] = EXPECTED_BASELINE_VALUES[name]
        if len(restored) < preserved_count:
            raise RuntimeError("r1_post_write_appsettings_preservation_failed")
        updated = await self._arm(
            "PUT", config, body={"properties": restored}
        )
        current = restored = {}
        if updated.status_code not in {200, 201}:
            raise RuntimeError("r1_post_write_appsettings_restore_failed")
        restarted = await self._arm(
            "POST", f"{WEB_APP_ID}/restart?api-version={WEB_API}"
        )
        if restarted.status_code not in {200, 202, 204}:
            raise RuntimeError("r1_post_write_restart_failed")

    async def verify_closed_once(self) -> bool:
        config = (
            f"{WEB_APP_ID}/config/appsettings/list?api-version={WEB_API}"
        )
        current = self._bounded_properties(await self._arm("POST", config))
        switches_ok = all(
            current.get(name) == EXPECTED_BASELINE_VALUES[name]
            for name in SWITCH_ORDER
        )
        current = {}
        assignment = (
            f"{VAULT_ID}/providers/Microsoft.Authorization/roleAssignments/"
            f"{WRITER_ROLE_ASSIGNMENT_ID}?api-version={AUTH_API}"
        )
        absent = await self._arm("GET", assignment)
        return switches_ok and absent.status_code == 404

    async def close(self) -> None:
        await self._http.aclose()
        await self._credential.close()


class R1PostWritePersistentHostExecutor:
    """One claim, one effect phase, one post-restart verification phase."""

    __slots__ = (
        "_checkpoint", "_control_factory", "_session_close", "_store",
    )

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        store: PersistentHostCloseStore,
        session_close: Callable[[], Awaitable[bool]],
        control_factory=ExactManagedIdentityPostWriteControl,
    ) -> None:
        if (
            not isinstance(checkpoint_path, Path)
            or not isinstance(store, PersistentHostCloseStore)
            or not callable(session_close)
            or not callable(control_factory)
        ):
            raise TypeError("r1_post_write_host_executor_dependency_invalid")
        self._checkpoint = checkpoint_path
        self._store = store
        self._session_close = session_close
        self._control_factory = control_factory

    async def __call__(self) -> PostWriteCloseResult:
        state = self._store.read()
        if state is None:
            if (
                not verify_consumed_write_checkpoint(self._checkpoint)
                or not self._store.claim_once()
            ):
                return self._no_go("checkpoint")
            state = HostCloseState("CLAIMED")
        if state.phase == "RESTART-REQUESTED":
            control = self._control_factory()
            try:
                verified = await control.verify_closed_once() is True
            finally:
                await control.close()
            if not verified:
                self._store.replace(HostCloseState("NO-GO"))
                return self._no_go("post_restart")
            self._store.replace(HostCloseState(
                "VERIFIED", True, True, True
            ))
            return PostWriteCloseResult(
                "VERIFIED-RESTORED", True, True, True, True, 0,
                resources_closed=True,
            )
        if state.phase != "CLAIMED":
            return self._no_go("persistent_state")

        control = self._control_factory()
        try:
            if await control.preflight_once() is not True:
                self._store.replace(HostCloseState("NO-GO"))
                return self._no_go("preflight")
            session_ok = await self._session_close() is True
            key_vault_ok = await control.close_writer_once() is True
            if not session_ok or not key_vault_ok:
                self._store.replace(HostCloseState(
                    "NO-GO", session_ok, key_vault_ok, False
                ))
                return self._no_go(
                    "session" if not session_ok else "key_vault"
                )
            self._store.replace(HostCloseState(
                "RESTART-REQUESTED", True, True, True
            ))
            await control.restore_switches_and_restart_once()
            return self._no_go("restart_pending")
        except BaseException:
            current = self._store.read()
            if current is None or current.phase != "RESTART-REQUESTED":
                self._store.replace(HostCloseState("NO-GO"))
            return self._no_go("host_effect")
        finally:
            await control.close()

    @staticmethod
    def _no_go(surface: str) -> PostWriteCloseResult:
        return PostWriteCloseResult(
            "NO-GO-REMAINDER", True, False, False, False, 0,
            failure_surface=surface, resources_closed=True,
        )


__all__ = [
    "DEFAULT_STATE_PATH", "ExactManagedIdentityPostWriteControl",
    "HostCloseState", "PersistentHostCloseStore",
    "R1PostWritePersistentHostExecutor",
]
