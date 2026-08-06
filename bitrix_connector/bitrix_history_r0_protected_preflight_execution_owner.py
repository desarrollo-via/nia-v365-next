"""Owner one-shot que ensambla M6 y M7 detrás de la frase M7."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_protected_preflight_execution_gate import (
    PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
    ProtectedPreflightExecutionGateSnapshot,
    main as execute_gate_entrypoint,
)
from .bitrix_history_r0_protected_preflight_launcher import (
    PreparedProtectedPreflightLauncher,
    compose_real_ready_launcher,
)
from .bitrix_history_r0_protected_preflight_composition import (
    PROTECTED_PREFLIGHT_FAILURE_CATEGORIES,
)


LauncherComposer = Callable[[], PreparedProtectedPreflightLauncher]
ExecutionGateEntrypoint = Callable[..., int]
_GATE_RESULT_KEYS = frozenset(
    field.name for field in fields(ProtectedPreflightExecutionGateSnapshot)
)
_BOOL_KEYS = frozenset(
    {
        "protected_source_opened",
        "resources_closed",
        "identity_diagnostic_available",
        "chat_id_matches",
        "dialog_id_matches",
        "entity_type_matches",
        "role_allowed",
        "anchor_available",
        "connector_locked_off",
        "persisted",
        "nia_called",
        "bitrix_written",
    }
)
_COUNT_KEYS = frozenset(
    {
        "launcher_calls",
        "source_read_calls",
        "preflight_calls",
        "dialog_read_calls",
        "history_read_calls",
        "mutation_calls",
        "identity_mismatch_count",
    }
)


@dataclass(frozen=True)
class ProtectedPreflightExecutionOwnerSnapshot:
    state: Literal["READY", "NO-GO", "CANCELLED"] = "NO-GO"
    reason: str = "protected_preflight_execution_owner_not_started"
    failure_category: str = "none"
    launcher_compositions: int = 0
    gate_calls: int = 0
    launcher_calls: int = 0
    protected_source_opened: bool = False
    resources_closed: bool = True
    source_read_calls: int = 0
    preflight_calls: int = 0
    dialog_read_calls: int = 0
    history_read_calls: int = 0
    mutation_calls: int = 0
    identity_diagnostic_available: bool = False
    chat_id_matches: bool = False
    dialog_id_matches: bool = False
    entity_type_matches: bool = False
    role_allowed: bool = False
    identity_mismatch_count: int = 0
    anchor_available: bool = False
    connector_locked_off: bool = True
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


def _parse_owner_request(argv: Sequence[str]) -> Path | None:
    values = tuple(argv)
    if (
        len(values) != 4
        or values[0] != "--confirm-code"
        or values[1] != PROTECTED_PREFLIGHT_REAL_CONFIRMATION
        or values[2] != "--dotenv-path"
        or not values[3]
    ):
        return None
    try:
        return Path(values[3])
    except (TypeError, ValueError):
        return None


def _emit(snapshot: ProtectedPreflightExecutionOwnerSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


def _validated_gate_result(
    payload: object,
    *,
    exit_code: object,
) -> ProtectedPreflightExecutionOwnerSnapshot:
    if not isinstance(payload, Mapping) or frozenset(payload) != _GATE_RESULT_KEYS:
        raise TypeError("protected_preflight_execution_owner_result_invalid")
    if any(type(payload[key]) is not bool for key in _BOOL_KEYS):
        raise TypeError("protected_preflight_execution_owner_result_invalid")
    if any(
        type(payload[key]) is not int or payload[key] < 0 for key in _COUNT_KEYS
    ):
        raise TypeError("protected_preflight_execution_owner_result_invalid")
    if (
        type(payload["failure_category"]) is not str
        or payload["failure_category"] not in PROTECTED_PREFLIGHT_FAILURE_CATEGORIES
    ):
        raise TypeError("protected_preflight_execution_owner_result_invalid")

    state = payload["state"]
    expected_code = {"READY": 0, "NO-GO": 1, "CANCELLED": 130}.get(state)
    if expected_code is None or type(exit_code) is not int or exit_code != expected_code:
        raise TypeError("protected_preflight_execution_owner_result_invalid")
    if payload["launcher_calls"] != 1:
        raise TypeError("protected_preflight_execution_owner_attempt_invalid")
    if (
        payload["connector_locked_off"] is not True
        or payload["persisted"] is not False
        or payload["nia_called"] is not False
        or payload["bitrix_written"] is not False
        or payload["mutation_calls"] != 0
    ):
        raise TypeError("protected_preflight_execution_owner_barrier_degraded")
    if state == "READY" and (
        payload["failure_category"] != "none"
        or
        payload["resources_closed"] is not True
        or payload["anchor_available"] is not True
        or payload["preflight_calls"] != 1
        or payload["dialog_read_calls"] != 1
        or payload["history_read_calls"] != 0
    ):
        raise TypeError("protected_preflight_execution_owner_ready_invalid")
    if state == "NO-GO" and payload["failure_category"] == "none":
        raise TypeError("protected_preflight_execution_owner_no_go_category_missing")
    diagnostic_values = (
        payload["chat_id_matches"],
        payload["dialog_id_matches"],
        payload["entity_type_matches"],
        payload["role_allowed"],
    )
    if payload["identity_diagnostic_available"]:
        if (
            payload["failure_category"] != "dialog_identity_mismatch"
            or payload["identity_mismatch_count"]
            != sum(not value for value in diagnostic_values)
            or not 1 <= payload["identity_mismatch_count"] <= 4
        ):
            raise TypeError(
                "protected_preflight_execution_owner_identity_diagnostic_invalid"
            )
    elif any(diagnostic_values) or payload["identity_mismatch_count"] != 0:
        raise TypeError(
            "protected_preflight_execution_owner_identity_diagnostic_invalid"
        )

    reason = {
        "READY": "protected_preflight_execution_owner_ready",
        "NO-GO": "protected_preflight_execution_owner_no_go",
        "CANCELLED": "protected_preflight_execution_owner_cancelled",
    }[state]
    return ProtectedPreflightExecutionOwnerSnapshot(
        state=state,
        reason=reason,
        failure_category=payload["failure_category"],
        launcher_compositions=1,
        gate_calls=1,
        launcher_calls=payload["launcher_calls"],
        protected_source_opened=payload["protected_source_opened"],
        resources_closed=payload["resources_closed"],
        source_read_calls=payload["source_read_calls"],
        preflight_calls=payload["preflight_calls"],
        dialog_read_calls=payload["dialog_read_calls"],
        history_read_calls=payload["history_read_calls"],
        mutation_calls=payload["mutation_calls"],
        identity_diagnostic_available=payload["identity_diagnostic_available"],
        chat_id_matches=payload["chat_id_matches"],
        dialog_id_matches=payload["dialog_id_matches"],
        entity_type_matches=payload["entity_type_matches"],
        role_allowed=payload["role_allowed"],
        identity_mismatch_count=payload["identity_mismatch_count"],
        anchor_available=payload["anchor_available"],
        connector_locked_off=payload["connector_locked_off"],
        persisted=payload["persisted"],
        nia_called=payload["nia_called"],
        bitrix_written=payload["bitrix_written"],
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    compose_launcher: LauncherComposer = compose_real_ready_launcher,
    execute_gate: ExecutionGateEntrypoint = execute_gate_entrypoint,
) -> int:
    """Compone e invoca una vez; una frase inválida no alcanza la composición."""

    selected_argv = tuple(sys.argv[1:] if argv is None else argv)
    if _parse_owner_request(selected_argv) is None:
        snapshot = ProtectedPreflightExecutionOwnerSnapshot(
            reason="protected_preflight_execution_owner_rejected"
        )
        _emit(snapshot)
        return 2

    captured = io.StringIO()
    launcher_compositions = 0
    gate_calls = 0
    try:
        launcher_compositions = 1
        launcher = compose_launcher()
        if type(launcher) is not PreparedProtectedPreflightLauncher:
            raise TypeError("protected_preflight_execution_owner_launcher_invalid")
        gate_calls = 1
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            exit_code = execute_gate(selected_argv, launcher=launcher)
        payload = json.loads(captured.getvalue())
        snapshot = _validated_gate_result(payload, exit_code=exit_code)
    except KeyboardInterrupt:
        snapshot = ProtectedPreflightExecutionOwnerSnapshot(
            state="CANCELLED",
            reason="protected_preflight_execution_owner_cancelled",
            launcher_compositions=launcher_compositions,
            gate_calls=gate_calls,
            resources_closed=False,
        )
    except BaseException:
        snapshot = ProtectedPreflightExecutionOwnerSnapshot(
            reason="protected_preflight_execution_owner_failed_safe",
            launcher_compositions=launcher_compositions,
            gate_calls=gate_calls,
            resources_closed=(gate_calls == 0),
        )
    finally:
        captured.seek(0)
        captured.truncate(0)
        captured.close()

    _emit(snapshot)
    if snapshot.state == "READY":
        return 0
    if snapshot.state == "CANCELLED":
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ProtectedPreflightExecutionOwnerSnapshot", "main"]
