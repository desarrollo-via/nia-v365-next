"""Continuidad privada entre el preflight protegido y el handoff en memoria."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_handoff import (
    ArmedReader,
    AuthorizationGate,
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
)
from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .bitrix_history_r0_preflight_composition import (
    BitrixHistoryClientBuilder,
    StoredOAuthResourcesFactory,
    execute_stored_oauth_history_preflight_once,
)
from .bitrix_history_r0_protected_helper import (
    ProtectedHelperSnapshot,
    ProtectedHelperState,
)
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
    ProtectedSourceBuilder,
    execute_protected_dotenv_settings_once,
)
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_preflight_composition import (
    classify_protected_preflight_failure,
)
from .bitrix_history_r0_protected_reader_failure import (
    classify_protected_reader_failure,
)
from .bitrix_history_r0_protected_session_failure import (
    normalize_protected_session_failure_category,
)
from .bitrix_history_r0_runner import BitrixHistoryR0Result, BitrixHistoryR0Status
from .config import ConnectorSettings, load_settings


ProtectedOutcomeExecutor = Callable[..., Awaitable[BitrixHistoryR0PreflightOutcome]]
ProtectedHandoffBuilder = Callable[
    [BitrixHistoryR0PreflightOutcome], BitrixHistoryR0InMemoryHandoff
]
ProtectedSettingsCapture = Callable[[ConnectorSettings], None]


def _ignore_settings(_settings: ConnectorSettings) -> None:
    return None


@dataclass(frozen=True)
class ProtectedHandoffContinuitySnapshot:
    state: Literal[
        "WAITING-AUTHORIZATION",
        "ARMED",
        "RECEIVED",
        "NO-GO",
        "CANCELLED",
        "CLOSED",
    ]
    reason: str
    failure_category: str = "none"
    protected_source_opened: bool = False
    required_values_present: bool = False
    settings_operation_completed: bool = False
    source_read_calls: int = 0
    preflight_calls: int = 0
    authorization_calls: int = 0
    reader_calls: int = 0
    dialog_read_calls: int = 0
    history_read_calls: int = 0
    mutation_calls: int = 0
    anchor_available: bool = False
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    resources_closed: bool = False


class ProtectedInMemoryHandoffOwner:
    """Posee el handoff sin ofrecer acceso al objeto de ancla ni serializarlo."""

    __slots__ = (
        "_authorization_calls",
        "_handoff",
        "_helper",
        "_preflight_calls",
        "_reader_calls",
        "_reader_result",
        "_failure_category",
    )

    def __init__(
        self,
        *,
        helper: ProtectedHelperSnapshot,
        handoff: BitrixHistoryR0InMemoryHandoff | None,
        preflight_calls: int,
        failure_category: str = "none",
    ) -> None:
        self._helper = helper
        self._handoff = handoff
        self._preflight_calls = preflight_calls
        self._authorization_calls = 0
        self._reader_calls = 0
        self._reader_result: BitrixHistoryR0Result | None = None
        self._failure_category = normalize_protected_session_failure_category(
            failure_category,
            fallback="other_safe_failure",
        )

    def __repr__(self) -> str:
        return "ProtectedInMemoryHandoffOwner(<redacted>)"

    def snapshot(self) -> ProtectedHandoffContinuitySnapshot:
        helper = self._helper
        if self._handoff is None:
            cancelled = helper.state is ProtectedHelperState.CANCELLED
            return ProtectedHandoffContinuitySnapshot(
                state="CANCELLED" if cancelled else "NO-GO",
                reason=(
                    "protected_handoff_continuity_cancelled"
                    if cancelled
                    else "protected_handoff_continuity_no_go"
                ),
                failure_category=("cancelled" if cancelled else self._failure_category),
                protected_source_opened=helper.protected_source_opened,
                required_values_present=helper.required_values_present,
                settings_operation_completed=helper.operation_completed,
                source_read_calls=helper.source_read_calls,
                preflight_calls=self._preflight_calls,
                authorization_calls=self._authorization_calls,
                reader_calls=self._reader_calls,
                resources_closed=(
                    helper.resources_closed and self._reader_calls == 0
                ),
            )

        handoff = self._handoff.snapshot()
        waiting = bool(
            helper.state is ProtectedHelperState.READY
            and helper.operation_completed
            and helper.resources_closed
            and handoff.state is BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION
            and handoff.preflight_ready
            and handoff.anchor_available
            and handoff.resources_closed
            and self._preflight_calls == 1
        )
        if waiting:
            public_state = "WAITING-AUTHORIZATION"
            reason = "protected_handoff_continuity_waiting_authorization"
            failure_category = "none"
        elif (
            helper.state is ProtectedHelperState.READY
            and helper.operation_completed
            and helper.resources_closed
            and handoff.state is BitrixHistoryR0HandoffState.ARMED
            and handoff.preflight_ready
            and handoff.anchor_available
            and handoff.history_armed
            and handoff.resources_closed
            and self._preflight_calls == 1
            and self._authorization_calls == 1
            and self._reader_calls == 0
        ):
            public_state = "ARMED"
            reason = "protected_handoff_continuity_armed"
            failure_category = "none"
        elif handoff.state is BitrixHistoryR0HandoffState.CLOSED:
            public_state = "CLOSED"
            reason = "protected_handoff_continuity_closed"
            failure_category = "none"
        elif handoff.state is BitrixHistoryR0HandoffState.CANCELLED:
            public_state = "CANCELLED"
            reason = "protected_handoff_continuity_cancelled"
            failure_category = "authorization_cancelled"
        elif self._reader_result is not None:
            result = self._reader_result
            received = bool(
                self._reader_calls == 1
                and result.status is BitrixHistoryR0Status.RECEIVED
                and result.controlled_message_verified
                and result.connector_locked_off
                and not result.persisted
                and not result.nia_called
                and not result.bitrix_written
                and result.resources_closed
            )
            public_state = "RECEIVED" if received else "NO-GO"
            reason = (
                "protected_handoff_continuity_received"
                if received
                else "protected_handoff_continuity_reader_no_go"
            )
            failure_category = (
                "none"
                if received
                else classify_protected_reader_failure(result)
            )
        else:
            public_state = "NO-GO"
            reason = "protected_handoff_continuity_no_go"
            failure_category = self._failure_category
        return ProtectedHandoffContinuitySnapshot(
            state=public_state,
            reason=reason,
            failure_category=failure_category,
            protected_source_opened=helper.protected_source_opened,
            required_values_present=helper.required_values_present,
            settings_operation_completed=helper.operation_completed,
            source_read_calls=helper.source_read_calls,
            preflight_calls=self._preflight_calls,
            authorization_calls=self._authorization_calls,
            reader_calls=self._reader_calls,
            dialog_read_calls=(
                self._reader_result.dialog_read_calls
                if self._reader_result is not None
                else handoff.dialog_read_calls
            ),
            history_read_calls=(
                self._reader_result.history_read_calls
                if self._reader_result is not None
                else handoff.history_read_calls
            ),
            mutation_calls=(
                self._reader_result.mutation_calls
                if self._reader_result is not None
                else handoff.mutation_calls
            ),
            anchor_available=(
                handoff.anchor_available
                if public_state in {"WAITING-AUTHORIZATION", "ARMED"}
                else False
            ),
            connector_locked_off=(
                self._reader_result.connector_locked_off
                if self._reader_result is not None
                else handoff.connector_locked_off
            ),
            persisted=(
                self._reader_result.persisted
                if self._reader_result is not None
                else handoff.persisted
            ),
            nia_called=(
                self._reader_result.nia_called
                if self._reader_result is not None
                else handoff.nia_called
            ),
            bitrix_written=(
                self._reader_result.bitrix_written
                if self._reader_result is not None
                else handoff.bitrix_written
            ),
            resources_closed=(
                helper.resources_closed
                and (
                    self._reader_result.resources_closed
                    if self._reader_result is not None
                    else handoff.resources_closed
                )
            ),
        )

    async def wait_for_authorization(
        self,
        *,
        authorization_gate: AuthorizationGate,
        timeout_seconds: float,
    ) -> ProtectedHandoffContinuitySnapshot:
        """Delega una sola autorización sin devolver el handoff ni el ancla."""

        if self._handoff is None or self.snapshot().state != "WAITING-AUTHORIZATION":
            return self.snapshot()
        self._authorization_calls = 1
        try:
            await self._handoff.wait_for_authorization(
                authorization_gate=authorization_gate,
                timeout_seconds=timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            try:
                await self._handoff.close()
            except Exception:
                pass
            self._handoff = None
        return self.snapshot()

    async def run_armed_reader_once(
        self,
        reader: ArmedReader,
    ) -> ProtectedHandoffContinuitySnapshot:
        """Entrega el ancla al lector una vez y publica sólo el snapshot."""

        if self._handoff is None or self.snapshot().state != "ARMED":
            return self.snapshot()
        self._reader_calls = 1
        try:
            result = await self._handoff.run_armed_reader_once(reader)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._failure_category = "reader_failed"
            try:
                await self._handoff.close()
            except Exception:
                pass
            self._handoff = None
            return self.snapshot()
        if type(result) is not BitrixHistoryR0Result:
            self._failure_category = "reader_other_safe_failure"
            try:
                await self._handoff.close()
            except Exception:
                pass
            self._handoff = None
            return self.snapshot()
        self._reader_result = result
        return self.snapshot()

    async def close(self) -> ProtectedHandoffContinuitySnapshot:
        if self._handoff is not None:
            await self._handoff.close()
        return self.snapshot()


def _handoff_snapshot_is_safe(handoff: BitrixHistoryR0InMemoryHandoff) -> bool:
    snapshot = handoff.snapshot()
    return bool(
        snapshot.history_read_calls == 0
        and snapshot.mutation_calls == 0
        and snapshot.connector_locked_off
        and not snapshot.persisted
        and not snapshot.nia_called
        and not snapshot.bitrix_written
    )


async def prepare_protected_dotenv_history_handoff_once(
    *,
    dotenv_path: Path,
    resources_factory: StoredOAuthResourcesFactory,
    client_builder: BitrixHistoryClientBuilder,
    timeout_seconds: float = 10.0,
    settings_loader: ProtectedSettingsLoader = load_settings,
    source_builder: ProtectedSourceBuilder = AllowlistedDotenvSource,
    execute_preflight: ProtectedOutcomeExecutor = (
        execute_stored_oauth_history_preflight_once
    ),
    handoff_builder: ProtectedHandoffBuilder = (
        BitrixHistoryR0InMemoryHandoff.from_preflight
    ),
    on_settings_ready: ProtectedSettingsCapture = _ignore_settings,
) -> ProtectedInMemoryHandoffOwner:
    """Conserva el ancla en el handoff; nunca la devuelve ni la serializa."""

    handoff: BitrixHistoryR0InMemoryHandoff | None = None
    prepared_settings: ConnectorSettings | None = None
    outcome: BitrixHistoryR0PreflightOutcome | None = None
    preflight_calls = 0

    async def prepare_handoff(settings: ConnectorSettings) -> None:
        nonlocal handoff, outcome, preflight_calls, prepared_settings
        preflight_calls = 1
        outcome = await execute_preflight(
            settings=settings,
            timeout_seconds=timeout_seconds,
            resources_factory=resources_factory,
            client_builder=client_builder,
        )
        if type(outcome) is not BitrixHistoryR0PreflightOutcome:
            raise TypeError("protected_handoff_outcome_invalid")
        candidate = handoff_builder(outcome)
        if type(candidate) is not BitrixHistoryR0InMemoryHandoff:
            raise TypeError("protected_handoff_candidate_invalid")
        handoff = candidate
        prepared_settings = settings

    helper = await execute_protected_dotenv_settings_once(
        dotenv_path=Path(dotenv_path),
        operation=prepare_handoff,
        settings_loader=settings_loader,
        source_builder=source_builder,
    )

    keep_handoff = bool(
        helper.state is ProtectedHelperState.READY
        and helper.operation_completed
        and helper.resources_closed
        and handoff is not None
        and _handoff_snapshot_is_safe(handoff)
    )
    if keep_handoff and prepared_settings is not None:
        try:
            capture_result = on_settings_ready(prepared_settings)
            if capture_result is not None:
                raise TypeError("protected_handoff_settings_capture_invalid")
        except Exception:
            keep_handoff = False
    if handoff is not None and not keep_handoff:
        try:
            await handoff.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            handoff = None
    prepared_settings = None

    failure_category = classify_protected_preflight_failure(
        helper=helper,
        outcome=outcome,
        preflight_calls=preflight_calls,
    )
    if (
        handoff is not None
        and handoff.snapshot().state
        is BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION
    ):
        failure_category = "none"

    return ProtectedInMemoryHandoffOwner(
        helper=helper,
        handoff=handoff,
        preflight_calls=preflight_calls,
        failure_category=failure_category,
    )


__all__ = [
    "ProtectedHandoffContinuitySnapshot",
    "ProtectedInMemoryHandoffOwner",
    "ProtectedOutcomeExecutor",
    "ProtectedSettingsCapture",
    "prepare_protected_dotenv_history_handoff_once",
]
