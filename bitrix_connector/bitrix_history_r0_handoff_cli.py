"""CLI inyectable para conservar el handoff R0 en el mismo proceso."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone

from .bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
    compose_stored_oauth_history_armed_reader,
)
from .bitrix_history_r0_handoff import (
    MAX_AUTHORIZATION_WAIT_SECONDS,
    ArmedReader,
    BitrixHistoryR0HandoffDecision,
    BitrixHistoryR0HandoffSnapshot,
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
    prepare_stored_oauth_history_handoff_once,
)
from .bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0WaitingMessageSnapshot,
)
from .bitrix_history_r0_preflight_cli import HISTORY_R0_PREFLIGHT_CONFIRMATION
from .bitrix_history_r0_preflight_composition import (
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
)
from .config import ConnectorSettings, load_settings


HISTORY_R0_ARM_CONFIRMATION = (
    "ARMAR HISTORIAL CHAT78733 SIN ENVIAR MENSAJE"
)
MAX_CONTROLLED_TEXT_CHARACTERS = 4096

SettingsLoader = Callable[[], ConnectorSettings]
ConfirmationReader = Callable[[], Awaitable[str]]
ExpectedHashReader = Callable[[], Awaitable[str]]
HandoffPreparer = Callable[..., Awaitable[BitrixHistoryR0InMemoryHandoff]]
ArmedReaderComposer = Callable[..., ArmedReader]
UtcNow = Callable[[], datetime]
HandoffOutput = (
    BitrixHistoryR0HandoffSnapshot
    | BitrixHistoryR0WaitingMessageSnapshot
    | BitrixHistoryR0Result
)
SnapshotEmitter = Callable[[HandoffOutput], None]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara y retiene el handoff R0 sin leer historial.",
    )
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=(HISTORY_R0_PREFLIGHT_CONFIRMATION,),
    )
    parser.add_argument(
        "--preflight-timeout-seconds",
        type=float,
        default=DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--authorization-wait-seconds",
        type=float,
        default=MAX_AUTHORIZATION_WAIT_SECONDS,
    )
    parser.add_argument(
        "--armed-hold-seconds",
        type=float,
        default=MAX_AUTHORIZATION_WAIT_SECONDS,
    )
    return parser


async def _read_second_confirmation() -> str:
    try:
        import msvcrt
    except ImportError as exc:  # pragma: no cover - CLI manual sólo en Windows
        raise RuntimeError("bitrix_history_console_unavailable") from exc

    print("Segunda confirmación R0: ", end="", flush=True)
    received: list[str] = []
    try:
        while True:
            await asyncio.sleep(0.05)
            while msvcrt.kbhit():
                character = msvcrt.getwch()
                if character in {"\r", "\n"}:
                    print()
                    return "".join(received)
                if character == "\x03":
                    raise asyncio.CancelledError
                if character == "\b":
                    if received:
                        received.pop()
                    continue
                if character.isprintable() and len(received) < 128:
                    received.append(character)
    except asyncio.CancelledError:
        print()
        raise


async def _read_expected_text_sha256() -> str:
    try:
        import msvcrt
    except ImportError as exc:  # pragma: no cover - CLI manual sólo en Windows
        raise RuntimeError("bitrix_history_console_unavailable") from exc

    print("Texto controlado esperado (entrada oculta): ", end="", flush=True)
    received: list[str] = []
    try:
        while True:
            await asyncio.sleep(0.05)
            while msvcrt.kbhit():
                character = msvcrt.getwch()
                if character in {"\r", "\n"}:
                    print()
                    if not received:
                        raise RuntimeError("bitrix_history_expected_text_empty")
                    plaintext = "".join(received)
                    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
                if character == "\x03":
                    raise asyncio.CancelledError
                if character == "\b":
                    if received:
                        received.pop()
                    continue
                if character.isprintable():
                    if len(received) >= MAX_CONTROLLED_TEXT_CHARACTERS:
                        print()
                        raise RuntimeError("bitrix_history_expected_text_too_long")
                    received.append(character)
    except asyncio.CancelledError:
        print()
        raise
    finally:
        for index in range(len(received)):
            received[index] = "\0"
        received.clear()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _emit_json(output: HandoffOutput) -> None:
    print(json.dumps(output.model_dump(mode="json"), sort_keys=True))


def _failed_safe(
    reason: str,
    *,
    resources_closed: bool = False,
) -> BitrixHistoryR0HandoffSnapshot:
    return BitrixHistoryR0HandoffSnapshot(
        state=BitrixHistoryR0HandoffState.NO_GO,
        reason=reason,
        resources_closed=resources_closed,
    )


async def execute_handoff_cli_session(
    *,
    settings: ConnectorSettings,
    preflight_timeout_seconds: float,
    authorization_wait_seconds: float,
    armed_hold_seconds: float,
    confirmation_reader: ConfirmationReader,
    prepare_handoff: HandoffPreparer,
    emit: SnapshotEmitter,
    armed_stage: ArmedReader | None = None,
    expected_hash_reader: ExpectedHashReader = _read_expected_text_sha256,
    armed_reader_composer: ArmedReaderComposer = (
        compose_stored_oauth_history_armed_reader
    ),
    utc_now: UtcNow = _utc_now,
) -> HandoffOutput:
    """Mantiene el handoff vivo y nunca ejecuta historial por sí misma."""

    handoff = await prepare_handoff(
        settings=settings,
        timeout_seconds=preflight_timeout_seconds,
    )
    initial = handoff.snapshot()
    emit(initial)
    if initial.state is not BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION:
        return initial

    async def authorization_gate() -> BitrixHistoryR0HandoffDecision:
        received = await confirmation_reader()
        if hmac.compare_digest(received, HISTORY_R0_ARM_CONFIRMATION):
            return BitrixHistoryR0HandoffDecision.ARM
        return BitrixHistoryR0HandoffDecision.CANCEL

    decision = await handoff.wait_for_authorization(
        authorization_gate=authorization_gate,
        timeout_seconds=authorization_wait_seconds,
    )
    emit(decision)
    if decision.state is not BitrixHistoryR0HandoffState.ARMED:
        await handoff.close()
        return decision

    try:
        if armed_hold_seconds <= 0 or armed_hold_seconds > MAX_AUTHORIZATION_WAIT_SECONDS:
            return _failed_safe(
                "bitrix_history_armed_hold_invalid",
                resources_closed=True,
            )
        async def run_armed_reader() -> BitrixHistoryR0Result:
            selected_reader = armed_stage
            if selected_reader is None:
                expected_hash = await expected_hash_reader()
                ephemeral_inputs = BitrixHistoryR0EphemeralInputs(
                    expected_text_sha256=expected_hash,
                    window_start=utc_now(),
                )

                async def emit_waiting_message(
                    snapshot: BitrixHistoryR0WaitingMessageSnapshot,
                ) -> None:
                    emit(snapshot)

                selected_reader = armed_reader_composer(
                    settings=settings,
                    inputs=ephemeral_inputs,
                    timeout_seconds=preflight_timeout_seconds,
                    on_waiting_message=emit_waiting_message,
                )
            return await handoff.run_armed_reader_once(selected_reader)

        reader_result = await asyncio.wait_for(
            run_armed_reader(),
            timeout=armed_hold_seconds,
        )
        emit(reader_result)
        return reader_result
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return _failed_safe(
            "bitrix_history_armed_hold_timeout",
            resources_closed=True,
        )
    except Exception:
        return _failed_safe(
            "bitrix_history_armed_stage_failed_safe",
            resources_closed=True,
        )
    finally:
        closed = await handoff.close()
        emit(closed)


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_loader: SettingsLoader = load_settings,
    confirmation_reader: ConfirmationReader = _read_second_confirmation,
    prepare_handoff: HandoffPreparer = prepare_stored_oauth_history_handoff_once,
    emit: SnapshotEmitter = _emit_json,
    armed_stage: ArmedReader | None = None,
    expected_hash_reader: ExpectedHashReader = _read_expected_text_sha256,
    armed_reader_composer: ArmedReaderComposer = (
        compose_stored_oauth_history_armed_reader
    ),
    utc_now: UtcNow = _utc_now,
) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = settings_loader()
        result = asyncio.run(
            execute_handoff_cli_session(
                settings=settings,
                preflight_timeout_seconds=args.preflight_timeout_seconds,
                authorization_wait_seconds=args.authorization_wait_seconds,
                armed_hold_seconds=args.armed_hold_seconds,
                confirmation_reader=confirmation_reader,
                prepare_handoff=prepare_handoff,
                armed_stage=armed_stage,
                emit=emit,
                expected_hash_reader=expected_hash_reader,
                armed_reader_composer=armed_reader_composer,
                utc_now=utc_now,
            )
        )
    except asyncio.CancelledError:
        result = _failed_safe("bitrix_history_handoff_cli_cancelled")
        emit(result)
        return 130
    except Exception:
        result = _failed_safe("bitrix_history_handoff_cli_failed_safe")
        emit(result)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "HISTORY_R0_ARM_CONFIRMATION",
    "MAX_CONTROLLED_TEXT_CHARACTERS",
    "execute_handoff_cli_session",
    "main",
]
