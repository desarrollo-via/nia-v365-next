"""CLI one-shot del R0 controlado; no se importa desde el proceso web."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

from .config import ConnectorSettings, load_settings
from .openline_r0_runner import (
    CONTROLLED_R0_CONFIRMATION,
    ControlledR0RunnerResult,
    ControlledR0RunnerStatus,
    execute_controlled_r0_runner,
)
from .openline_r0_receipt import R0ReceiptGate
from .openline_r0_bridge_client import HttpR0ReceiptGate
from .review_auth import SingleReviewerAuthenticator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def build_http_r0_receipt_gate(
    settings: ConnectorSettings,
) -> Optional[R0ReceiptGate]:
    """Compone el cliente solo con switch explícito y barreras cerradas."""

    if not settings.r0_bridge_configuration_valid:
        raise ValueError("r0_bridge_switch_invalid")
    if not settings.r0_bridge_enabled:
        return None
    if (
        settings.requested_mode != "off"
        or settings.effective_mode.value != "off"
        or not settings.activation_locked
        or settings.external_calls_enabled
        or settings.pilot_enabled
        or not settings.pilot_emergency_stop
        or not settings.pilot_configuration_valid
    ):
        raise ValueError("r0_bridge_safety_state_invalid")
    if not all(
        (
            settings.g0_public_origin,
            settings.review_token,
            settings.review_actor,
            settings.review_credential_id,
        )
    ):
        raise ValueError("r0_bridge_client_configuration_missing")
    if not SingleReviewerAuthenticator(
        review_token=settings.review_token,
        actor=settings.review_actor,
        credential_id=settings.review_credential_id,
    ).configured:
        raise ValueError("r0_bridge_client_configuration_invalid")
    return HttpR0ReceiptGate(
        public_origin=settings.g0_public_origin,
        review_token=settings.review_token,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta una vinculacion R0 temporal de la Linea 13 y exige "
            "rollback verificado. Requiere autorizacion externa separada."
        )
    )
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=[CONTROLLED_R0_CONFIRMATION],
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser


def _load_local_settings() -> ConnectorSettings:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    return load_settings(values)


async def execute_cli_once(
    *,
    confirmation: str,
    timeout_seconds: float,
    settings: ConnectorSettings,
    receipt_gate: Optional[R0ReceiptGate] = None,
    runner: Callable[..., Awaitable[ControlledR0RunnerResult]] = (
        execute_controlled_r0_runner
    ),
) -> ControlledR0RunnerResult:
    return await runner(
        confirmation=confirmation,
        settings=settings,
        receipt_gate=receipt_gate,
        timeout_seconds=timeout_seconds,
    )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    settings_loader: Callable[[], ConnectorSettings] = _load_local_settings,
    receipt_gate_factory: Callable[
        [ConnectorSettings], Optional[R0ReceiptGate]
    ] = build_http_r0_receipt_gate,
    execute_once: Callable[..., Awaitable[ControlledR0RunnerResult]] = (
        execute_cli_once
    ),
) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = settings_loader()
        result = asyncio.run(
            execute_once(
                confirmation=args.confirm_code,
                timeout_seconds=args.timeout_seconds,
                settings=settings,
                receipt_gate=receipt_gate_factory(settings),
            )
        )
    except Exception:
        result = ControlledR0RunnerResult(
            status=ControlledR0RunnerStatus.BLOCKED,
            reason="r0_cli_failed_safe",
        )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status is ControlledR0RunnerStatus.RESTORED else 1


if __name__ == "__main__":
    raise SystemExit(main())
