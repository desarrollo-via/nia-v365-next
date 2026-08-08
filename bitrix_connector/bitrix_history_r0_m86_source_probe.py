"""M86-S: sonda one-shot inerte y exclusiva para la fuente M84/M81."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
    execute_injected_windows_credential_helper_once,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_protected_helper import (
    ProtectedFailureCategory,
    ProtectedHelperState,
)


M86S_SOURCE_PROBE_CONFIRMATION_TEXT = (
    "AUTORIZACIÓN SONDA M84/M81 — UNA SOLA LECTURA: Autorizo exclusivamente "
    "una única tentativa de lectura del target exacto "
    "nia-next/bitrix-r1/protected-settings/v1 mediante CredReadW, sin enumerar "
    "otras credenciales, para validar sólo en memoria el formato binario M84 y "
    "el contrato agregado M81, sin mostrar, copiar, transcribir, contar ni "
    "registrar valores; todos los buffers deben limpiarse y todos los recursos "
    "cerrarse en finally. Autorizo únicamente una salida pública categórica y "
    "no autorizo fallback, entorno, dotenv, OAuth, Mongo, red, Bitrix, NIA, "
    "historial, mensajes, escrituras, borrados, reintentos ni cambios "
    "productivos. Cualquier deriva o cierre ambiguo consume la autorización y "
    "termina en NO-GO."
)


@dataclass(frozen=True)
class M86SourceProbeSnapshot:
    phase: Literal["M86-S"]
    state: Literal["PREPARED", "READY", "NO-GO", "CANCELLED"]
    reason: str
    execution_requested: bool
    confirmation_exact: bool
    authorization_consumed: bool
    probe_calls: int
    exact_source_attempts: int
    protected_source_opened: bool
    required_values_present: bool
    aggregate_buffer_reads: int
    resources_closed: bool
    failure_category: ProtectedFailureCategory
    retry_budget: Literal[0] = 0
    exact_target_only: Literal[True] = True
    exact_read_budget: Literal[1] = 1
    enumeration_budget: Literal[0] = 0
    write_budget: Literal[0] = 0
    delete_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    oauth_calls: Literal[0] = 0
    mongo_calls: Literal[0] = 0
    network_calls: Literal[0] = 0
    bitrix_calls: Literal[0] = 0
    nia_calls: Literal[0] = 0
    history_calls: Literal[0] = 0
    message_calls: Literal[0] = 0
    values_exposed: Literal[False] = False
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    bitrix_written: Literal[False] = False
    authorization_decision: Literal["REQUEST"] = "REQUEST"


class M86SourceProbeOwner:
    """Posee una sola fuente; preview y builder real no la abren."""

    __slots__ = ("_backend", "_execution_enabled", "_used")

    def __init__(
        self,
        *,
        backend: InjectedWindowsCredentialBackend,
        execution_enabled: bool = False,
    ) -> None:
        if (
            backend is None
            or not callable(getattr(backend, "fetch_exact", None))
            or not callable(getattr(backend, "close", None))
            or type(execution_enabled) is not bool
        ):
            raise TypeError("m86s_source_probe_dependency_invalid")
        self._backend: Optional[InjectedWindowsCredentialBackend] = backend
        self._execution_enabled = execution_enabled
        self._used = False

    def __repr__(self) -> str:
        return "M86SourceProbeOwner(<redacted>)"

    @staticmethod
    def _snapshot(
        *,
        state: str,
        reason: str,
        execution_requested: bool,
        confirmation_exact: bool = False,
        authorization_consumed: bool = False,
        probe_calls: int = 0,
        exact_source_attempts: int = 0,
        protected_source_opened: bool = False,
        required_values_present: bool = False,
        aggregate_buffer_reads: int = 0,
        resources_closed: bool = True,
        failure_category: ProtectedFailureCategory = "none",
    ) -> M86SourceProbeSnapshot:
        return M86SourceProbeSnapshot(
            phase="M86-S",
            state=state,
            reason=reason,
            execution_requested=execution_requested,
            confirmation_exact=confirmation_exact,
            authorization_consumed=authorization_consumed,
            probe_calls=probe_calls,
            exact_source_attempts=exact_source_attempts,
            protected_source_opened=protected_source_opened,
            required_values_present=required_values_present,
            aggregate_buffer_reads=aggregate_buffer_reads,
            resources_closed=resources_closed,
            failure_category=failure_category,
        )

    def preview(self) -> M86SourceProbeSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86s_source_probe_inert",
            execution_requested=False,
        )

    async def run_once(
        self,
        *,
        execute: bool = False,
        confirmation: Optional[str] = None,
    ) -> M86SourceProbeSnapshot:
        if not execute:
            return self.preview()
        if self._used or self._backend is None:
            self._used = True
            return self._snapshot(
                state="NO-GO",
                reason="m86s_source_probe_reuse_rejected",
                execution_requested=True,
            )
        self._used = True
        exact = confirmation == M86S_SOURCE_PROBE_CONFIRMATION_TEXT
        if not self._execution_enabled or not exact:
            closed = await self._close_backend_once()
            return self._snapshot(
                state="NO-GO",
                reason=(
                    "m86s_source_probe_execution_not_enabled"
                    if not self._execution_enabled
                    else "m86s_source_probe_confirmation_invalid"
                ),
                execution_requested=True,
                confirmation_exact=exact,
                authorization_consumed=exact,
                resources_closed=closed,
                failure_category=(
                    "none" if closed else "protected_resources_close_failed"
                ),
            )

        backend, self._backend = self._backend, None

        async def accept_aggregate_contract(_values) -> None:
            return None

        try:
            result = await execute_injected_windows_credential_helper_once(
                backend=backend,
                operation=accept_aggregate_contract,
            )
        except BaseException:
            try:
                await backend.close()
            except BaseException:
                closed = False
            else:
                closed = True
            return self._snapshot(
                state="NO-GO",
                reason="m86s_source_probe_failed_safe",
                execution_requested=True,
                confirmation_exact=True,
                authorization_consumed=True,
                probe_calls=1,
                exact_source_attempts=1,
                resources_closed=closed,
                failure_category=(
                    "protected_source_open_failed"
                    if closed
                    else "protected_resources_close_failed"
                ),
            )

        state = (
            "READY"
            if result.state is ProtectedHelperState.READY
            else "CANCELLED"
            if result.state is ProtectedHelperState.CANCELLED
            else "NO-GO"
        )
        return self._snapshot(
            state=state,
            reason=(
                "m86s_source_probe_ready"
                if state == "READY"
                else "m86s_source_probe_cancelled"
                if state == "CANCELLED"
                else "m86s_source_probe_no_go"
            ),
            execution_requested=True,
            confirmation_exact=True,
            authorization_consumed=True,
            probe_calls=1,
            exact_source_attempts=1,
            protected_source_opened=result.protected_source_opened,
            required_values_present=result.required_values_present,
            aggregate_buffer_reads=result.source_read_calls,
            resources_closed=result.resources_closed,
            failure_category=result.failure_category,
        )

    async def _close_backend_once(self) -> bool:
        backend, self._backend = self._backend, None
        if backend is None:
            return True
        try:
            await backend.close()
        except BaseException:
            return False
        return True


def build_real_m86_source_probe_owner(
    *, execution_enabled: bool = False
) -> M86SourceProbeOwner:
    """Enlaza M84 real sin cargar DLL ni abrir Credential Manager."""

    return M86SourceProbeOwner(
        backend=build_real_windows_credential_backend(),
        execution_enabled=execution_enabled,
    )


__all__ = [
    "M86S_SOURCE_PROBE_CONFIRMATION_TEXT",
    "M86SourceProbeOwner",
    "M86SourceProbeSnapshot",
    "build_real_m86_source_probe_owner",
]
