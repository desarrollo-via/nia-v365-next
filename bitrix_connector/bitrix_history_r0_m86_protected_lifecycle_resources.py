"""M86-H: recursos protegidos vivos durante preflight, espera y M88."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
)
from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthBackend,
    M82Status,
    StoredOAuthAccessView,
    execute_m82_injected_settings_oauth_once,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_m86_stored_oauth_backend import (
    build_real_m86_stored_oauth_backend,
)
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
)
from .bitrix_history_r0_protected_helper import ProtectedFailureCategory
from .config import ConnectorSettings, load_settings


M86H_MAX_LIFETIME_SECONDS = 300.0


PreflightOperation = Callable[
    [ConnectorSettings, StoredOAuthAccessView], Awaitable[object]
]
CrossTurnOperation = Callable[
    [ConnectorSettings, StoredOAuthAccessView, object], Awaitable[None]
]
M88Operation = Callable[
    [ConnectorSettings, StoredOAuthAccessView, object], Awaitable[object]
]


@dataclass(frozen=True)
class M86ProtectedLifecycleSnapshot:
    phase: Literal["M86-H"]
    state: Literal[
        "PREPARED",
        "VERIFIED",
        "ROLLED-BACK",
        "NO-GO",
        "CANCELLED",
        "TIMED-OUT",
    ]
    reason: str
    execution_requested: bool
    owner_calls: int
    credential_source_read_calls: int
    settings_load_calls: int
    oauth_load_calls: int
    oauth_refresh_calls: Literal[0]
    oauth_token_view_reads: int
    preflight_calls: int
    cross_turn_calls: int
    m88_calls: int
    same_settings_view_used: bool
    same_oauth_view_used: bool
    same_private_outcome_used: bool
    private_outcome_persisted: Literal[False]
    credential_close_verified: bool
    oauth_close_verified: bool
    private_resources_closed: bool
    protected_failure_category: ProtectedFailureCategory
    maximum_lifetime_seconds: float
    retry_budget: Literal[0] = 0
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    protected_source_bound: Literal[True] = True
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    remaining_real_bindings: Literal[2] = 2
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86ProtectedLifecycleResourceOwner:
    """Mantiene un único scope M82 abierto durante las tres operaciones."""

    __slots__ = (
        "_credential_backend",
        "_cross_turn_operation",
        "_execution_enabled",
        "_lifetime_seconds",
        "_m88_operation",
        "_oauth_backend",
        "_preflight_operation",
        "_settings_loader",
        "_used",
    )

    def __init__(
        self,
        *,
        credential_backend: InjectedWindowsCredentialBackend,
        oauth_backend: InjectedStoredOAuthBackend,
        preflight_operation: PreflightOperation,
        cross_turn_operation: CrossTurnOperation,
        m88_operation: M88Operation,
        settings_loader: ProtectedSettingsLoader = load_settings,
        execution_enabled: bool = False,
        lifetime_seconds: float = M86H_MAX_LIFETIME_SECONDS,
    ) -> None:
        if (
            credential_backend is None
            or oauth_backend is None
            or not all(
                callable(value)
                for value in (
                    preflight_operation,
                    cross_turn_operation,
                    m88_operation,
                    settings_loader,
                )
            )
            or type(execution_enabled) is not bool
            or type(lifetime_seconds) not in (int, float)
            or lifetime_seconds <= 0
            or lifetime_seconds > M86H_MAX_LIFETIME_SECONDS
        ):
            raise TypeError("m86h_resource_owner_dependency_invalid")
        self._credential_backend: Optional[InjectedWindowsCredentialBackend] = (
            credential_backend
        )
        self._oauth_backend: Optional[InjectedStoredOAuthBackend] = oauth_backend
        self._preflight_operation: Optional[PreflightOperation] = preflight_operation
        self._cross_turn_operation: Optional[CrossTurnOperation] = cross_turn_operation
        self._m88_operation: Optional[M88Operation] = m88_operation
        self._settings_loader: Optional[ProtectedSettingsLoader] = settings_loader
        self._execution_enabled = execution_enabled
        self._lifetime_seconds = float(lifetime_seconds)
        self._used = False

    def __repr__(self) -> str:
        return "M86ProtectedLifecycleResourceOwner(<redacted>)"

    def _snapshot(
        self,
        *,
        state: str,
        reason: str,
        execution_requested: bool,
        owner_calls: int = 0,
        credential_source_read_calls: int = 0,
        settings_load_calls: int = 0,
        oauth_load_calls: int = 0,
        oauth_token_view_reads: int = 0,
        preflight_calls: int = 0,
        cross_turn_calls: int = 0,
        m88_calls: int = 0,
        same_settings_view_used: bool = False,
        same_oauth_view_used: bool = False,
        same_private_outcome_used: bool = False,
        credential_close_verified: bool = True,
        oauth_close_verified: bool = True,
        private_resources_closed: bool = True,
        protected_failure_category: ProtectedFailureCategory = "none",
    ) -> M86ProtectedLifecycleSnapshot:
        return M86ProtectedLifecycleSnapshot(
            phase="M86-H",
            state=state,
            reason=reason,
            execution_requested=execution_requested,
            owner_calls=owner_calls,
            credential_source_read_calls=credential_source_read_calls,
            settings_load_calls=settings_load_calls,
            oauth_load_calls=oauth_load_calls,
            oauth_refresh_calls=0,
            oauth_token_view_reads=oauth_token_view_reads,
            preflight_calls=preflight_calls,
            cross_turn_calls=cross_turn_calls,
            m88_calls=m88_calls,
            same_settings_view_used=same_settings_view_used,
            same_oauth_view_used=same_oauth_view_used,
            same_private_outcome_used=same_private_outcome_used,
            private_outcome_persisted=False,
            credential_close_verified=credential_close_verified,
            oauth_close_verified=oauth_close_verified,
            private_resources_closed=private_resources_closed,
            protected_failure_category=protected_failure_category,
            maximum_lifetime_seconds=self._lifetime_seconds,
        )

    def preview(self) -> M86ProtectedLifecycleSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86h_protected_lifecycle_resources_inert",
            execution_requested=False,
        )

    async def run_once(self, *, execute: bool = False) -> M86ProtectedLifecycleSnapshot:
        if not execute:
            return self.preview()
        if not self._execution_enabled:
            return self._snapshot(
                state="NO-GO",
                reason="m86h_execution_not_enabled",
                execution_requested=True,
            )
        if self._used or self._credential_backend is None:
            self._used = True
            return self._snapshot(
                state="NO-GO",
                reason="m86h_resource_owner_reuse_rejected",
                execution_requested=True,
            )
        self._used = True
        credential, self._credential_backend = self._credential_backend, None
        oauth, self._oauth_backend = self._oauth_backend, None
        preflight, self._preflight_operation = self._preflight_operation, None
        cross_turn, self._cross_turn_operation = self._cross_turn_operation, None
        m88, self._m88_operation = self._m88_operation, None
        settings_loader, self._settings_loader = self._settings_loader, None
        if None in (oauth, preflight, cross_turn, m88, settings_loader):
            return self._snapshot(
                state="NO-GO",
                reason="m86h_resource_owner_dependencies_consumed",
                execution_requested=True,
                owner_calls=1,
                private_resources_closed=False,
            )

        calls = {"preflight": 0, "cross_turn": 0, "m88": 0}
        identities: dict[str, tuple[int, int, int]] = {}
        lifecycle_state = "NO-GO"
        lifecycle_reason = "m86h_lifecycle_operation_failed_safe"

        async def lifecycle_operation(settings, token_view):
            nonlocal lifecycle_state, lifecycle_reason
            calls["preflight"] = 1
            outcome = await preflight(settings, token_view)
            require_anchor = getattr(outcome, "require_anchor", None)
            if not callable(require_anchor) or require_anchor() is None:
                raise RuntimeError("m86h_preflight_outcome_invalid")
            identities["preflight"] = (id(settings), id(token_view), id(outcome))

            calls["cross_turn"] = 1
            await cross_turn(settings, token_view, outcome)
            identities["cross_turn"] = (id(settings), id(token_view), id(outcome))

            calls["m88"] = 1
            result = await m88(settings, token_view, outcome)
            identities["m88"] = (id(settings), id(token_view), id(outcome))
            result_state = getattr(result, "state", None)
            if result_state not in ("VERIFIED", "ROLLED-BACK"):
                raise RuntimeError("m86h_m88_result_invalid")
            lifecycle_state = result_state
            lifecycle_reason = (
                "m86h_protected_lifecycle_verified"
                if result_state == "VERIFIED"
                else "m86h_protected_lifecycle_rolled_back"
            )

        task = asyncio.create_task(
            execute_m82_injected_settings_oauth_once(
                credential_backend=credential,
                oauth_backend=oauth,
                operation=lifecycle_operation,
                settings_loader=settings_loader,
            )
        )
        try:
            done, _pending = await asyncio.wait(
                {task},
                timeout=self._lifetime_seconds,
            )
            timed_out = task not in done
            if timed_out:
                task.cancel()
            m82 = await task
        except asyncio.CancelledError:
            task.cancel()
            try:
                await task
            except BaseException:
                pass
            return self._snapshot(
                state="CANCELLED",
                reason="m86h_lifecycle_cancelled",
                execution_requested=True,
                owner_calls=1,
                preflight_calls=calls["preflight"],
                cross_turn_calls=calls["cross_turn"],
                m88_calls=calls["m88"],
            )
        except BaseException:
            if not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            return self._snapshot(
                state="NO-GO",
                reason="m86h_resource_scope_failed_safe",
                execution_requested=True,
                owner_calls=1,
                preflight_calls=calls["preflight"],
                cross_turn_calls=calls["cross_turn"],
                m88_calls=calls["m88"],
                private_resources_closed=False,
            )

        if timed_out:
            return self._snapshot(
                state="TIMED-OUT",
                reason="m86h_lifetime_expired",
                execution_requested=True,
                owner_calls=1,
                credential_source_read_calls=m82.credential_source_read_calls,
                settings_load_calls=m82.settings_load_calls,
                oauth_load_calls=m82.oauth_load_calls,
                oauth_token_view_reads=m82.oauth_token_view_reads,
                preflight_calls=calls["preflight"],
                cross_turn_calls=calls["cross_turn"],
                m88_calls=calls["m88"],
                credential_close_verified=m82.credential_close_verified,
                oauth_close_verified=m82.oauth_close_verified,
                private_resources_closed=m82.private_resources_closed,
                protected_failure_category=m82.protected_failure_category,
            )

        same_identity = (
            len(identities) == 3
            and identities["preflight"]
            == identities["cross_turn"]
            == identities["m88"]
        )
        ready = (
            m82.status is M82Status.READY
            and lifecycle_state in ("VERIFIED", "ROLLED-BACK")
            and same_identity
            and m82.credential_source_read_calls == 7
            and m82.settings_load_calls == 1
            and m82.oauth_load_calls == 1
            and m82.oauth_refresh_calls == 0
            and m82.private_resources_closed
        )
        state = lifecycle_state if ready else (
            "CANCELLED" if m82.status is M82Status.CANCELLED else "NO-GO"
        )
        reason = lifecycle_reason if ready else (
            "m86h_lifecycle_cancelled"
            if state == "CANCELLED"
            else "m86h_protected_lifecycle_failed_safe"
        )
        return self._snapshot(
            state=state,
            reason=reason,
            execution_requested=True,
            owner_calls=1,
            credential_source_read_calls=m82.credential_source_read_calls,
            settings_load_calls=m82.settings_load_calls,
            oauth_load_calls=m82.oauth_load_calls,
            oauth_token_view_reads=m82.oauth_token_view_reads,
            preflight_calls=calls["preflight"],
            cross_turn_calls=calls["cross_turn"],
            m88_calls=calls["m88"],
            same_settings_view_used=same_identity,
            same_oauth_view_used=same_identity,
            same_private_outcome_used=same_identity,
            credential_close_verified=m82.credential_close_verified,
            oauth_close_verified=m82.oauth_close_verified,
            private_resources_closed=m82.private_resources_closed,
            protected_failure_category=m82.protected_failure_category,
        )


async def _unbound_preflight(_settings, _token_view):
    raise RuntimeError("m86h_real_preflight_operation_unbound")


async def _unbound_cross_turn(_settings, _token_view, _outcome):
    raise RuntimeError("m86h_real_cross_turn_operation_unbound")


async def _unbound_m88(_settings, _token_view, _outcome):
    raise RuntimeError("m86h_real_m88_operation_unbound")


def build_real_m86_protected_lifecycle_resource_owner(
) -> M86ProtectedLifecycleResourceOwner:
    """Enlaza factories reales sin abrir fuente, OAuth ni operación alguna."""

    return M86ProtectedLifecycleResourceOwner(
        credential_backend=build_real_windows_credential_backend(),
        oauth_backend=build_real_m86_stored_oauth_backend(),
        preflight_operation=_unbound_preflight,
        cross_turn_operation=_unbound_cross_turn,
        m88_operation=_unbound_m88,
        execution_enabled=False,
    )


__all__ = [
    "M86H_MAX_LIFETIME_SECONDS",
    "M86ProtectedLifecycleResourceOwner",
    "M86ProtectedLifecycleSnapshot",
    "build_real_m86_protected_lifecycle_resource_owner",
]
