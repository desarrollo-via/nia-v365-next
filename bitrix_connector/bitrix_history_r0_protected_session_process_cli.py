"""CLI one-shot para la sesión R0 protegida dentro de un único proceso."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_handoff_cli import HISTORY_R0_ARM_CONFIRMATION
from .bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionExecutionPlan,
)
from .bitrix_history_r0_protected_session_process_owner import (
    PreparedProtectedHistorySessionProcessOwner,
    ProtectedHistorySessionProcessOwnerSnapshot,
    compose_protected_history_session_process_owner,
)
from .bitrix_history_r0_protected_session_real_parser_adapter import (
    PROTECTED_SESSION_REAL_CONFIRMATION,
)
from .bitrix_history_r0_runner import BitrixHistoryR0WaitingMessageSnapshot
from .bitrix_history_r0_protected_session_failure import (
    normalize_protected_session_failure_category,
)
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE = (
    r'.\.venv\Scripts\python.exe -m '
    r'bitrix_connector.bitrix_history_r0_protected_session_process_cli '
    r'--confirm-code "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ" '
    r'--dotenv-path .env '
    r'--expected-text-sha256 "<EXPECTED_TEXT_SHA256>" '
    r'--window-start-utc "<WINDOW_START_UTC>" '
    r'--arm-code "ARMAR HISTORIAL CHAT78733 SIN ENVIAR MENSAJE"'
)

Dependency = Callable[..., object]
SnapshotEmitter = Callable[[object], None]


@dataclass(frozen=True, repr=False)
class _ProtectedSessionProcessRequest:
    dotenv_path: Path
    expected_text_sha256: str
    window_start: datetime

    def __repr__(self) -> str:
        return "_ProtectedSessionProcessRequest(<redacted>)"


@dataclass(frozen=True)
class ProtectedSessionProcessWaitingSnapshot:
    state: Literal["WAITING-MESSAGE"] = "WAITING-MESSAGE"
    reason: str = "protected_history_session_process_waiting_message"
    waiting_message_signals: int = 1
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


@dataclass(frozen=True)
class ProtectedSessionProcessCliSnapshot:
    state: Literal["RECEIVED", "CANCELLED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_process_cli_not_started"
    failure_category: str = "none"
    request_valid: bool = False
    resources_factory_compositions: int = 0
    plan_compositions: int = 0
    owner_compositions: int = 0
    owner_calls: int = 0
    waiting_message_signals: int = 0
    same_process_continuity_bound: bool = True
    private_state_cleared: bool = True
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


def _parse_utc(value: str) -> datetime | None:
    try:
        candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if candidate.tzinfo is None or candidate.utcoffset() != timezone.utc.utcoffset(None):
        return None
    return candidate


def _parse_request(argv: Sequence[str]) -> _ProtectedSessionProcessRequest | None:
    values = tuple(argv)
    if (
        len(values) != 10
        or values[0] != "--confirm-code"
        or values[1] != PROTECTED_SESSION_REAL_CONFIRMATION
        or values[2] != "--dotenv-path"
        or not values[3]
        or values[4] != "--expected-text-sha256"
        or values[6] != "--window-start-utc"
        or values[8] != "--arm-code"
        or values[9] != HISTORY_R0_ARM_CONFIRMATION
    ):
        return None
    window_start = _parse_utc(values[7])
    if window_start is None:
        return None
    try:
        inputs = BitrixHistoryR0EphemeralInputs(
            expected_text_sha256=values[5],
            window_start=window_start,
        )
        return _ProtectedSessionProcessRequest(
            dotenv_path=Path(values[3]),
            expected_text_sha256=inputs.expected_text_sha256,
            window_start=inputs.window_start,
        )
    except (TypeError, ValueError):
        return None


def _emit_json(snapshot: object) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True), flush=True)


async def execute_protected_session_process_cli_once(
    *,
    request: _ProtectedSessionProcessRequest,
    emit: SnapshotEmitter = _emit_json,
    resources_factory_builder: Dependency = PilotDiscoveryOAuthFactory,
    preflight_client_builder: Dependency = BitrixHistoryR0Client,
    reader_client_builder: Dependency = BitrixHistoryR0Client,
    plan_builder: Dependency = ProtectedHistorySessionExecutionPlan,
    compose_owner: Dependency = compose_protected_history_session_process_owner,
) -> ProtectedSessionProcessCliSnapshot:
    """Materializa y consume una única sesión; publica sólo snapshots allowlisted."""

    resources_factory_compositions = 0
    plan_compositions = 0
    owner_compositions = 0
    owner_calls = 0
    waiting_message_signals = 0

    async def on_waiting_message(snapshot: BitrixHistoryR0WaitingMessageSnapshot) -> None:
        nonlocal waiting_message_signals
        if (
            type(snapshot) is not BitrixHistoryR0WaitingMessageSnapshot
            or waiting_message_signals != 0
        ):
            raise TypeError("protected_history_session_waiting_signal_invalid")
        waiting_message_signals = 1
        emit(ProtectedSessionProcessWaitingSnapshot())

    try:
        if type(request) is not _ProtectedSessionProcessRequest:
            raise TypeError("protected_history_session_process_cli_request_invalid")
        resources_factory_compositions = 1
        resources_factory = resources_factory_builder()
        if not callable(getattr(resources_factory, "build", None)):
            raise TypeError("protected_history_session_process_cli_resources_invalid")
        inputs = BitrixHistoryR0EphemeralInputs(
            expected_text_sha256=request.expected_text_sha256,
            window_start=request.window_start,
        )

        async def inner_confirmation_reader() -> str:
            return HISTORY_R0_ARM_CONFIRMATION

        plan_compositions = 1
        plan = plan_builder(
            dotenv_path=request.dotenv_path,
            inputs=inputs,
            resources_factory=resources_factory,
            preflight_client_builder=preflight_client_builder,
            reader_client_builder=reader_client_builder,
            confirmation_reader=inner_confirmation_reader,
            on_waiting_message=on_waiting_message,
            preflight_timeout_seconds=10.0,
            authorization_timeout_seconds=300.0,
            reader_timeout_seconds=300.0,
        )
        if type(plan) is not ProtectedHistorySessionExecutionPlan:
            raise TypeError("protected_history_session_process_cli_plan_invalid")
        owner_compositions = 1
        owner = compose_owner()
        if type(owner) is not PreparedProtectedHistorySessionProcessOwner:
            raise TypeError("protected_history_session_process_cli_owner_invalid")
        owner_calls = 1
        result = await owner.execute_once(execute=True, plan=plan)
        if type(result) is not ProtectedHistorySessionProcessOwnerSnapshot:
            raise TypeError("protected_history_session_process_cli_result_invalid")
        if (
            result.same_process_continuity_bound is not True
            or result.private_state_cleared is not True
            or result.connector_locked_off is not True
            or result.persisted is not False
            or result.nia_called is not False
            or result.bitrix_written is not False
            or result.state not in ("RECEIVED", "CANCELLED", "NO-GO")
        ):
            raise TypeError("protected_history_session_process_cli_barrier_degraded")
        return ProtectedSessionProcessCliSnapshot(
            state=result.state,
            reason={
                "RECEIVED": "protected_history_session_process_cli_received",
                "CANCELLED": "protected_history_session_process_cli_cancelled",
                "NO-GO": "protected_history_session_process_cli_no_go",
            }[result.state],
            failure_category=normalize_protected_session_failure_category(
                result.failure_category,
                fallback="other_safe_failure",
            ),
            request_valid=True,
            resources_factory_compositions=1,
            plan_compositions=1,
            owner_compositions=1,
            owner_calls=1,
            waiting_message_signals=waiting_message_signals,
            private_state_cleared=result.private_state_cleared,
            connector_locked_off=result.connector_locked_off,
            persisted=result.persisted,
            nia_called=result.nia_called,
            bitrix_written=result.bitrix_written,
        )
    except asyncio.CancelledError:
        return ProtectedSessionProcessCliSnapshot(
            state="CANCELLED",
            reason="protected_history_session_process_cli_cancelled",
            request_valid=True,
            resources_factory_compositions=resources_factory_compositions,
            plan_compositions=plan_compositions,
            owner_compositions=owner_compositions,
            owner_calls=owner_calls,
            waiting_message_signals=waiting_message_signals,
            private_state_cleared=False,
        )
    except BaseException:
        return ProtectedSessionProcessCliSnapshot(
            reason="protected_history_session_process_cli_failed_safe",
            failure_category="cli_failed",
            request_valid=True,
            resources_factory_compositions=resources_factory_compositions,
            plan_compositions=plan_compositions,
            owner_compositions=owner_compositions,
            owner_calls=owner_calls,
            waiting_message_signals=waiting_message_signals,
            private_state_cleared=(owner_calls == 0),
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    emit: SnapshotEmitter = _emit_json,
    resources_factory_builder: Dependency = PilotDiscoveryOAuthFactory,
    preflight_client_builder: Dependency = BitrixHistoryR0Client,
    reader_client_builder: Dependency = BitrixHistoryR0Client,
    plan_builder: Dependency = ProtectedHistorySessionExecutionPlan,
    compose_owner: Dependency = compose_protected_history_session_process_owner,
) -> int:
    selected_argv = tuple(sys.argv[1:] if argv is None else argv)
    request = _parse_request(selected_argv)
    if request is None:
        emit(
            ProtectedSessionProcessCliSnapshot(
                reason="protected_history_session_process_cli_rejected"
            )
        )
        return 2
    try:
        snapshot = asyncio.run(
            execute_protected_session_process_cli_once(
                request=request,
                emit=emit,
                resources_factory_builder=resources_factory_builder,
                preflight_client_builder=preflight_client_builder,
                reader_client_builder=reader_client_builder,
                plan_builder=plan_builder,
                compose_owner=compose_owner,
            )
        )
    except KeyboardInterrupt:
        snapshot = ProtectedSessionProcessCliSnapshot(
            state="CANCELLED",
            reason="protected_history_session_process_cli_cancelled",
            request_valid=True,
            private_state_cleared=False,
        )
    emit(snapshot)
    if snapshot.state == "RECEIVED":
        return 0
    if snapshot.state == "CANCELLED":
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE",
    "ProtectedSessionProcessCliSnapshot",
    "ProtectedSessionProcessWaitingSnapshot",
    "execute_protected_session_process_cli_once",
    "main",
]
