"""Proceso propietario M24, limitado a composición fixture-only R0."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from .bitrix_history_r0_protected_session_gate_owner import (
    ConfirmationReader,
    ProtectedHistorySessionGateOwnerSnapshot,
    execute_materialized_history_session_gate_once,
)
from .bitrix_history_r0_protected_session_plan_materializer import (
    MaterializedProtectedHistorySessionPlan,
)


PROTECTED_SESSION_FIXTURE_CONFIRMATION = (
    "VALIDAR OWNER SESION R0 SOLO CON DOBLES FICTICIOS"
)
PROTECTED_SESSION_FIXTURE_SOURCE = "fixture"

SessionBuilder = Callable[[], object]
OwnerExecutor = Callable[..., Awaitable[object]]
SnapshotEmitter = Callable[[object], None]


@dataclass(frozen=True)
class ProtectedHistorySessionCliSnapshot:
    state: Literal["RECEIVED", "CANCELLED", "NO-GO"] = "NO-GO"
    reason: str = "protected_history_session_cli_not_started"
    source: str = "fixture"
    builder_calls: int = 0
    owner_calls: int = 0
    private_state_cleared: bool = True
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False
    real_source_opened: bool = False
    external_calls: int = 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida el owner protegido R0 únicamente con dobles.",
    )
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=(PROTECTED_SESSION_FIXTURE_CONFIRMATION,),
    )
    parser.add_argument(
        "--protected-source",
        required=True,
        choices=(PROTECTED_SESSION_FIXTURE_SOURCE,),
    )
    return parser


def _fail_closed_session_builder() -> object:
    raise RuntimeError("protected_history_session_fixture_builder_required")


async def _fail_closed_confirmation_reader() -> str:
    raise RuntimeError("protected_history_session_fixture_confirmation_required")


def _emit_json(snapshot: ProtectedHistorySessionCliSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


async def execute_fixture_protected_session_owner_once(
    *,
    confirm_code: str,
    protected_source: str,
    session_builder: SessionBuilder,
    confirmation_reader: ConfirmationReader,
    owner_executor: OwnerExecutor = execute_materialized_history_session_gate_once,
) -> ProtectedHistorySessionCliSnapshot:
    """Compone y consume una sesión ficticia; no conoce fuentes reales."""

    if (
        confirm_code != PROTECTED_SESSION_FIXTURE_CONFIRMATION
        or protected_source != PROTECTED_SESSION_FIXTURE_SOURCE
        or not callable(session_builder)
        or not callable(confirmation_reader)
        or not callable(owner_executor)
    ):
        return ProtectedHistorySessionCliSnapshot(
            reason="protected_history_session_cli_fixture_rejected"
        )

    materialized: MaterializedProtectedHistorySessionPlan | None = None
    try:
        materialized = session_builder()
        if type(materialized) is not MaterializedProtectedHistorySessionPlan:
            raise TypeError("protected_history_session_cli_materialized_invalid")
        result = await owner_executor(
            materialized=materialized,
            confirmation_reader=confirmation_reader,
        )
        if type(result) is not ProtectedHistorySessionGateOwnerSnapshot:
            raise TypeError("protected_history_session_cli_result_invalid")
        if (
            result.private_state_cleared is not True
            or result.connector_locked_off is not True
            or result.persisted is not False
            or result.nia_called is not False
            or result.bitrix_written is not False
            or result.cleanup_calls != 1
        ):
            raise TypeError("protected_history_session_cli_barrier_degraded")
        if result.state not in ("RECEIVED", "CANCELLED", "NO-GO"):
            raise TypeError("protected_history_session_cli_state_invalid")
        return ProtectedHistorySessionCliSnapshot(
            state=result.state,
            reason={
                "RECEIVED": "protected_history_session_cli_fixture_received",
                "CANCELLED": "protected_history_session_cli_fixture_cancelled",
                "NO-GO": "protected_history_session_cli_fixture_no_go",
            }[result.state],
            builder_calls=1,
            owner_calls=1,
        )
    except asyncio.CancelledError:
        return ProtectedHistorySessionCliSnapshot(
            state="CANCELLED",
            reason="protected_history_session_cli_fixture_cancelled",
            builder_calls=int(materialized is not None),
            owner_calls=int(materialized is not None),
        )
    except BaseException:
        if materialized is not None:
            materialized.clear()
        return ProtectedHistorySessionCliSnapshot(
            reason="protected_history_session_cli_failed_safe",
            builder_calls=int(materialized is not None),
            owner_calls=0,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    session_builder: SessionBuilder = _fail_closed_session_builder,
    confirmation_reader: ConfirmationReader = _fail_closed_confirmation_reader,
    owner_executor: OwnerExecutor = execute_materialized_history_session_gate_once,
    emit: SnapshotEmitter = _emit_json,
) -> int:
    args = _parser().parse_args(argv)
    snapshot = asyncio.run(
        execute_fixture_protected_session_owner_once(
            confirm_code=args.confirm_code,
            protected_source=args.protected_source,
            session_builder=session_builder,
            confirmation_reader=confirmation_reader,
            owner_executor=owner_executor,
        )
    )
    emit(snapshot)
    return 0 if snapshot.state == "RECEIVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PROTECTED_SESSION_FIXTURE_CONFIRMATION",
    "PROTECTED_SESSION_FIXTURE_SOURCE",
    "ProtectedHistorySessionCliSnapshot",
    "execute_fixture_protected_session_owner_once",
    "main",
]
