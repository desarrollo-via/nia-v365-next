"""CLI protegida para ejecutar únicamente el preflight R0 de historial."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence

from .bitrix_history_r0_preflight import BitrixHistoryR0PreflightOutcome
from .bitrix_history_r0_preflight_composition import (
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    execute_stored_oauth_history_preflight_once,
)
from .bitrix_history_r0_runner import BitrixHistoryR0Result, BitrixHistoryR0Status
from .config import ConnectorSettings, load_settings


HISTORY_R0_PREFLIGHT_CONFIRMATION = (
    "PREPARAR ANCLA BITRIX CHAT78733 SOLO LECTURA"
)

SettingsLoader = Callable[[], ConnectorSettings]
PreflightExecutor = Callable[..., object]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecuta una sola lectura protegida para fijar el ancla R0.",
    )
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=(HISTORY_R0_PREFLIGHT_CONFIRMATION,),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    )
    return parser


def _failed_safe() -> BitrixHistoryR0Result:
    return BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.NO_GO,
        reason="bitrix_history_cli_failed_safe",
        dialog_read_calls=0,
        history_read_calls=0,
        resources_closed=False,
    )


def _emit(result: BitrixHistoryR0Result) -> None:
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_loader: SettingsLoader = load_settings,
    execute_once: PreflightExecutor = execute_stored_oauth_history_preflight_once,
) -> int:
    """Carga sólo el entorno del proceso tras la confirmación y emite allowlist."""

    args = _parser().parse_args(argv)
    try:
        settings = settings_loader()
        outcome = asyncio.run(
            execute_once(
                settings=settings,
                timeout_seconds=args.timeout_seconds,
            )
        )
        if not isinstance(outcome, BitrixHistoryR0PreflightOutcome):
            raise TypeError("bitrix_history_cli_outcome_invalid")
        result = outcome.result
    except Exception:
        result = _failed_safe()

    _emit(result)
    return 0 if result.status is BitrixHistoryR0Status.READY else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["HISTORY_R0_PREFLIGHT_CONFIRMATION", "main"]
