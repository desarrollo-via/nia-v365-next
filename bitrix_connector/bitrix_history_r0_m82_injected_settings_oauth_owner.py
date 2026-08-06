"""Composición M82 de settings y OAuth almacenado sólo con dobles inyectados."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Literal, Protocol

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
    WindowsCredentialProtectedValueSource,
)
from .bitrix_history_r0_protected_helper import (
    ProtectedFailureCategory,
    ProtectedHelperState,
)
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
    execute_protected_settings_once,
)
from .config import ConnectorSettings, load_settings


MAX_INJECTED_STORED_OAUTH_BYTES = 8 * 1024


def _zeroize(value: bytearray) -> None:
    value[:] = b"\x00" * len(value)


class InjectedStoredOAuthRecord:
    __slots__ = ("_token", "_used")

    def __init__(self, *, access_token: bytearray) -> None:
        self._token = access_token
        self._used = False

    def take_token_once(self) -> bytearray:
        if self._used:
            raise RuntimeError("m82_oauth_record_reused")
        self._used = True
        token, self._token = self._token, bytearray()
        return token

    def clear(self) -> None:
        if type(self._token) is bytearray:
            _zeroize(self._token)
        self._token = bytearray()
        self._used = True

    def __repr__(self) -> str:
        return "InjectedStoredOAuthRecord(<redacted>)"


class InjectedStoredOAuthBackend(Protocol):
    async def load_stored_once(
        self, settings: ConnectorSettings
    ) -> InjectedStoredOAuthRecord: ...

    async def close(self) -> None: ...


class StoredOAuthAccessView:
    __slots__ = ("_active", "_reads", "_token")

    def __init__(self, token: bytearray) -> None:
        self._token = token
        self._active = True
        self._reads = 0

    def read_text(self) -> str:
        if not self._active:
            raise RuntimeError("m82_oauth_view_closed")
        self._reads += 1
        return bytes(self._token).decode("utf-8")

    @property
    def reads(self) -> int:
        return self._reads

    def close(self) -> None:
        self._active = False

    def __repr__(self) -> str:
        return "StoredOAuthAccessView(<redacted>)"


class M82Status(str, Enum):
    READY = "READY"
    NO_GO = "NO-GO"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class StoredOAuthOwnerSnapshot:
    status: M82Status
    reason: str
    load_calls: int
    refresh_calls: Literal[0]
    operation_calls: int
    token_view_reads: int
    close_calls: int
    resources_closed: bool


StoredOAuthOperation = Callable[[StoredOAuthAccessView], Awaitable[None]]


class StoredOAuthNoRefreshResourceOwner:
    __slots__ = (
        "_backend", "_close_calls", "_closed", "_load_calls", "_used"
    )

    def __init__(self, *, backend: InjectedStoredOAuthBackend) -> None:
        if backend is None or not callable(getattr(backend, "load_stored_once", None)):
            raise TypeError("m82_oauth_backend_invalid")
        if not callable(getattr(backend, "close", None)):
            raise TypeError("m82_oauth_backend_invalid")
        self._backend: InjectedStoredOAuthBackend | None = backend
        self._close_calls = 0
        self._closed = False
        self._load_calls = 0
        self._used = False

    @property
    def load_calls(self) -> int:
        return self._load_calls

    @property
    def close_calls(self) -> int:
        return self._close_calls

    async def close_once(self) -> bool:
        backend, self._backend = self._backend, None
        if backend is None:
            return self._closed
        self._close_calls = 1
        try:
            await backend.close()
        except BaseException:
            self._closed = False
            return False
        self._closed = True
        return True

    async def run_once(
        self,
        *,
        settings: ConnectorSettings,
        operation: StoredOAuthOperation,
    ) -> StoredOAuthOwnerSnapshot:
        if self._used or self._backend is None:
            return StoredOAuthOwnerSnapshot(
                status=M82Status.NO_GO,
                reason="m82_oauth_owner_reuse_rejected",
                load_calls=0,
                refresh_calls=0,
                operation_calls=0,
                token_view_reads=0,
                close_calls=self._close_calls,
                resources_closed=self._closed,
            )
        self._used = True
        token = bytearray()
        record: InjectedStoredOAuthRecord | None = None
        view: StoredOAuthAccessView | None = None
        operation_calls = 0
        status = M82Status.NO_GO
        reason = "m82_oauth_owner_failed_safe"
        try:
            backend = self._backend
            if any(
                callable(getattr(backend, name, None))
                for name in ("refresh", "refresh_access_token")
            ):
                raise ValueError("m82_oauth_refresh_capability_rejected")
            self._load_calls = 1
            record = await backend.load_stored_once(settings)
            if type(record) is not InjectedStoredOAuthRecord:
                raise TypeError("m82_oauth_record_invalid")
            token = record.take_token_once()
            if (
                type(token) is not bytearray
                or not token
                or len(token) > MAX_INJECTED_STORED_OAUTH_BYTES
                or b"\x00" in token
            ):
                raise ValueError("m82_oauth_token_invalid")
            view = StoredOAuthAccessView(token)
            operation_calls = 1
            operation_result = await operation(view)
            if operation_result is not None:
                raise TypeError("m82_oauth_operation_result_invalid")
            status = M82Status.READY
            reason = "m82_stored_oauth_used_without_refresh"
        except asyncio.CancelledError:
            status = M82Status.CANCELLED
            reason = "m82_oauth_owner_cancelled"
        except Exception:
            status = M82Status.NO_GO
            reason = "m82_oauth_owner_failed_safe"
        finally:
            reads = view.reads if view is not None else 0
            if view is not None:
                view.close()
            if type(token) is bytearray:
                _zeroize(token)
            if type(record) is InjectedStoredOAuthRecord:
                record.clear()
            closed = await self.close_once()
            if not closed:
                status = M82Status.NO_GO
                reason = "m82_oauth_owner_close_failed"
        return StoredOAuthOwnerSnapshot(
            status=status,
            reason=reason,
            load_calls=self._load_calls,
            refresh_calls=0,
            operation_calls=operation_calls,
            token_view_reads=reads,
            close_calls=self._close_calls,
            resources_closed=self._closed,
        )

    def __repr__(self) -> str:
        return "StoredOAuthNoRefreshResourceOwner(<redacted>)"


M82Operation = Callable[
    [ConnectorSettings, StoredOAuthAccessView], Awaitable[None]
]


@dataclass(frozen=True)
class M82CompositionSnapshot:
    phase: Literal["M82"]
    status: M82Status
    reason: str
    credential_source_read_calls: int
    settings_load_calls: int
    oauth_load_calls: int
    oauth_refresh_calls: Literal[0]
    oauth_operation_calls: int
    oauth_token_view_reads: int
    credential_close_verified: bool
    oauth_close_calls: int
    oauth_close_verified: bool
    settings_off_locked_verified: bool
    private_resources_closed: bool
    protected_failure_category: ProtectedFailureCategory
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False


async def execute_m82_injected_settings_oauth_once(
    *,
    credential_backend: InjectedWindowsCredentialBackend,
    oauth_backend: InjectedStoredOAuthBackend,
    operation: M82Operation,
    settings_loader: ProtectedSettingsLoader = load_settings,
) -> M82CompositionSnapshot:
    """Compone M81, settings seguros y OAuth 1/0 bajo owners inyectados."""

    oauth_owner = StoredOAuthNoRefreshResourceOwner(backend=oauth_backend)
    oauth_snapshot: StoredOAuthOwnerSnapshot | None = None
    settings_load_calls = 0
    settings_verified = False

    async def settings_operation(settings: ConnectorSettings) -> None:
        nonlocal oauth_snapshot, settings_load_calls, settings_verified
        settings_load_calls = 1
        settings_verified = True

        async def oauth_operation(view: StoredOAuthAccessView) -> None:
            result = await operation(settings, view)
            if result is not None:
                raise TypeError("m82_composed_operation_result_invalid")

        oauth_snapshot = await oauth_owner.run_once(
            settings=settings,
            operation=oauth_operation,
        )
        if oauth_snapshot.status is M82Status.CANCELLED:
            raise asyncio.CancelledError()
        if oauth_snapshot.status is not M82Status.READY:
            raise RuntimeError("m82_oauth_stage_not_ready")

    source = WindowsCredentialProtectedValueSource(backend=credential_backend)
    helper_snapshot = await execute_protected_settings_once(
        source=source,
        operation=settings_operation,
        settings_loader=settings_loader,
    )
    oauth_closed = await oauth_owner.close_once()
    oauth_status = oauth_snapshot.status if oauth_snapshot is not None else None
    status = (
        M82Status.READY
        if helper_snapshot.state is ProtectedHelperState.READY
        and oauth_status is M82Status.READY
        and helper_snapshot.resources_closed
        and oauth_closed
        else (
            M82Status.CANCELLED
            if helper_snapshot.state is ProtectedHelperState.CANCELLED
            or oauth_status is M82Status.CANCELLED
            else M82Status.NO_GO
        )
    )
    failure_category = helper_snapshot.failure_category
    if status is M82Status.READY:
        failure_category = "none"
    elif status is M82Status.CANCELLED:
        failure_category = "cancelled"
    elif not helper_snapshot.resources_closed or not oauth_closed:
        failure_category = "protected_resources_close_failed"
    elif failure_category == "protected_operation_failed":
        if settings_load_calls == 0:
            failure_category = "protected_settings_validation_failed"
        elif oauth_snapshot is None or oauth_snapshot.operation_calls == 0:
            failure_category = "oauth_load_failed"
        else:
            failure_category = "lifecycle_operation_failed"
    return M82CompositionSnapshot(
        phase="M82",
        status=status,
        reason=(
            "m82_injected_settings_oauth_verified"
            if status is M82Status.READY
            else (
                "m82_injected_settings_oauth_cancelled"
                if status is M82Status.CANCELLED
                else "m82_injected_settings_oauth_no_go"
            )
        ),
        credential_source_read_calls=helper_snapshot.source_read_calls,
        settings_load_calls=settings_load_calls,
        oauth_load_calls=oauth_owner.load_calls,
        oauth_refresh_calls=0,
        oauth_operation_calls=(oauth_snapshot.operation_calls if oauth_snapshot else 0),
        oauth_token_view_reads=(oauth_snapshot.token_view_reads if oauth_snapshot else 0),
        credential_close_verified=helper_snapshot.resources_closed,
        oauth_close_calls=oauth_owner.close_calls,
        oauth_close_verified=oauth_closed,
        settings_off_locked_verified=settings_verified,
        private_resources_closed=helper_snapshot.resources_closed and oauth_closed,
        protected_failure_category=failure_category,
    )


__all__ = [
    "InjectedStoredOAuthBackend",
    "InjectedStoredOAuthRecord",
    "M82CompositionSnapshot",
    "M82Status",
    "MAX_INJECTED_STORED_OAUTH_BYTES",
    "StoredOAuthAccessView",
    "StoredOAuthNoRefreshResourceOwner",
    "StoredOAuthOwnerSnapshot",
    "execute_m82_injected_settings_oauth_once",
]
