import asyncio
import contextlib
import hashlib
import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from bitrix_connector.bitrix_history_r0_handoff import (
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
)
from bitrix_connector.bitrix_history_r0_handoff_cli import (
    HISTORY_R0_ARM_CONFIRMATION,
    _read_expected_text_sha256,
    execute_handoff_cli_session,
    main,
)
from bitrix_connector.bitrix_history_r0_preflight import BitrixHistoryR0Anchor
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
    BitrixHistoryR0WaitingMessageSnapshot,
)
from bitrix_connector.bitrix_history_r0_preflight_cli import (
    HISTORY_R0_PREFLIGHT_CONFIRMATION,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
CONTROLLED_TEXT = "mensaje controlado único"
CONTROLLED_HASH = hashlib.sha256(CONTROLLED_TEXT.encode("utf-8")).hexdigest()
FIXED_UTC = datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)


def waiting_handoff():
    return BitrixHistoryR0InMemoryHandoff(
        state=BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
        reason="bitrix_history_handoff_waiting_authorization",
        anchor=BitrixHistoryR0Anchor(900, 700),
        preflight_ready=True,
        dialog_read_calls=1,
        resources_closed=True,
    )


def reader_result():
    return BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.NO_GO,
        reason="bitrix_history_wait_timeout",
        dialog_read_calls=36,
        history_read_calls=0,
        baseline_captured=True,
        resources_closed=True,
    )


class BitrixHistoryR0HandoffCliTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(sys.platform == "win32", "requires Windows msvcrt")
    async def test_hidden_capture_hashes_internally_without_echoing_text(self):
        characters = iter([*CONTROLLED_TEXT, "\r"])
        output = io.StringIO()
        with (
            patch("msvcrt.kbhit", return_value=True),
            patch("msvcrt.getwch", side_effect=lambda: next(characters)),
            contextlib.redirect_stdout(output),
        ):
            digest = await _read_expected_text_sha256()

        self.assertEqual(digest, CONTROLLED_HASH)
        self.assertNotIn(CONTROLLED_TEXT, output.getvalue())
        self.assertNotIn(CONTROLLED_HASH, output.getvalue())

    async def test_after_arm_captures_hash_and_composes_reader_in_memory(self):
        handoff = waiting_handoff()
        calls = []
        composed = []
        emitted = []

        async def expected_hash_reader():
            calls.append("hash")
            return CONTROLLED_HASH

        def composer(**kwargs):
            calls.append("compose")
            composed.append(kwargs)

            async def reader(anchor):
                calls.append("reader")
                self.assertEqual(anchor.session_id, 900)
                await kwargs["on_waiting_message"](
                    BitrixHistoryR0WaitingMessageSnapshot()
                )
                return reader_result()

            return reader

        result = await execute_handoff_cli_session(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=5,
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            prepare_handoff=lambda **_kwargs: asyncio.sleep(0, result=handoff),
            emit=emitted.append,
            expected_hash_reader=expected_hash_reader,
            armed_reader_composer=composer,
            utc_now=lambda: FIXED_UTC,
        )

        self.assertEqual(result.reason, "bitrix_history_wait_timeout")
        self.assertEqual(calls, ["hash", "compose", "reader"])
        self.assertEqual(len(composed), 1)
        self.assertEqual(composed[0]["timeout_seconds"], 4)
        self.assertEqual(
            composed[0]["inputs"].expected_text_sha256,
            CONTROLLED_HASH,
        )
        self.assertEqual(composed[0]["inputs"].window_start, FIXED_UTC)
        self.assertEqual(composed[0]["inputs"].wait_seconds, 180)
        self.assertEqual(
            [getattr(output, "state", None) for output in emitted],
            [
                BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
                BitrixHistoryR0HandoffState.ARMED,
                "WAITING-MESSAGE",
                None,
                BitrixHistoryR0HandoffState.CLOSED,
            ],
        )
        self.assertEqual(
            emitted[2].model_dump(),
            BitrixHistoryR0WaitingMessageSnapshot().model_dump(),
        )
        self.assertFalse(handoff.snapshot().anchor_available)

    async def test_invalid_hash_or_capture_timeout_fails_closed_before_composer(self):
        composer_calls = []

        async def invalid_hash():
            return "invalid"

        invalid_handoff = waiting_handoff()
        invalid = await execute_handoff_cli_session(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=5,
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            prepare_handoff=lambda **_kwargs: asyncio.sleep(
                0,
                result=invalid_handoff,
            ),
            emit=lambda _output: None,
            expected_hash_reader=invalid_hash,
            armed_reader_composer=lambda **kwargs: composer_calls.append(kwargs),
            utc_now=lambda: FIXED_UTC,
        )
        self.assertEqual(
            invalid.reason,
            "bitrix_history_armed_stage_failed_safe",
        )
        self.assertEqual(composer_calls, [])
        self.assertFalse(invalid_handoff.snapshot().anchor_available)

        async def hold_hash():
            await asyncio.Event().wait()
            return CONTROLLED_HASH

        timeout_handoff = waiting_handoff()
        timeout = await execute_handoff_cli_session(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=0.001,
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            prepare_handoff=lambda **_kwargs: asyncio.sleep(
                0,
                result=timeout_handoff,
            ),
            emit=lambda _output: None,
            expected_hash_reader=hold_hash,
            armed_reader_composer=lambda **kwargs: composer_calls.append(kwargs),
            utc_now=lambda: FIXED_UTC,
        )
        self.assertEqual(timeout.reason, "bitrix_history_armed_hold_timeout")
        self.assertEqual(composer_calls, [])
        self.assertFalse(timeout_handoff.snapshot().anchor_available)

    async def test_exact_second_confirmation_runs_stage_in_same_process(self):
        handoff = waiting_handoff()
        emitted = []
        stage_calls = []

        async def prepare_handoff(**_kwargs):
            return handoff

        async def confirmation_reader():
            return HISTORY_R0_ARM_CONFIRMATION

        async def armed_stage(anchor):
            stage_calls.append(anchor)
            self.assertEqual(anchor.session_id, 900)
            self.assertEqual(anchor.baseline_last_message_id, 700)
            return reader_result()

        result = await execute_handoff_cli_session(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=5,
            confirmation_reader=confirmation_reader,
            prepare_handoff=prepare_handoff,
            armed_stage=armed_stage,
            emit=emitted.append,
        )

        self.assertEqual(result.status, BitrixHistoryR0Status.NO_GO)
        self.assertEqual(result.reason, "bitrix_history_wait_timeout")
        self.assertEqual(len(stage_calls), 1)
        self.assertEqual(
            [getattr(item, "state", None) for item in emitted],
            [
                BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
                BitrixHistoryR0HandoffState.ARMED,
                None,
                BitrixHistoryR0HandoffState.CLOSED,
            ],
        )
        self.assertEqual(emitted[2].reason, "bitrix_history_wait_timeout")
        self.assertFalse(handoff.snapshot().anchor_available)
        serialized = "".join(item.model_dump_json() for item in emitted)
        for forbidden in ("900", "700", "session_id", "last_message_id"):
            self.assertNotIn(forbidden, serialized)

    async def test_wrong_second_confirmation_cancels_before_stage(self):
        handoff = waiting_handoff()
        emitted = []
        stage_calls = 0

        async def stage(_anchor):
            nonlocal stage_calls
            stage_calls += 1
            return reader_result()

        result = await execute_handoff_cli_session(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=5,
            confirmation_reader=lambda: asyncio.sleep(0, result="incorrecta"),
            prepare_handoff=lambda **_kwargs: asyncio.sleep(0, result=handoff),
            armed_stage=stage,
            emit=emitted.append,
        )

        self.assertEqual(result.state, BitrixHistoryR0HandoffState.CANCELLED)
        self.assertEqual(stage_calls, 0)
        self.assertEqual(emitted[-1].state, BitrixHistoryR0HandoffState.CANCELLED)
        self.assertFalse(handoff.snapshot().anchor_available)

    async def test_no_go_never_reads_confirmation_or_runs_stage(self):
        no_go = BitrixHistoryR0InMemoryHandoff(
            state=BitrixHistoryR0HandoffState.NO_GO,
            reason="bitrix_history_barrier_degraded",
            resources_closed=True,
        )
        calls = []
        emitted = []

        async def forbidden_confirmation():
            calls.append("confirmation")
            return HISTORY_R0_ARM_CONFIRMATION

        async def forbidden_stage(_anchor):
            calls.append("stage")
            return reader_result()

        result = await execute_handoff_cli_session(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=5,
            confirmation_reader=forbidden_confirmation,
            prepare_handoff=lambda **_kwargs: asyncio.sleep(0, result=no_go),
            armed_stage=forbidden_stage,
            emit=emitted.append,
        )

        self.assertEqual(result.state, BitrixHistoryR0HandoffState.NO_GO)
        self.assertEqual(calls, [])
        self.assertEqual(emitted, [no_go.snapshot()])

    async def test_stage_timeout_failure_or_cancellation_always_closes(self):
        async def hold(_anchor):
            await asyncio.Event().wait()

        async def fail(_anchor):
            raise RuntimeError("protected detail")

        for stage, reason in (
            (hold, "bitrix_history_armed_hold_timeout"),
            (fail, "bitrix_history_armed_stage_failed_safe"),
        ):
            with self.subTest(reason=reason):
                handoff = waiting_handoff()
                emitted = []
                result = await execute_handoff_cli_session(
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                    preflight_timeout_seconds=4,
                    authorization_wait_seconds=5,
                    armed_hold_seconds=0.001,
                    confirmation_reader=lambda: asyncio.sleep(
                        0,
                        result=HISTORY_R0_ARM_CONFIRMATION,
                    ),
                    prepare_handoff=lambda **_kwargs: asyncio.sleep(
                        0,
                        result=handoff,
                    ),
                    armed_stage=stage,
                    emit=emitted.append,
                )
                self.assertEqual(result.reason, reason)
                self.assertFalse(handoff.snapshot().anchor_available)
                self.assertEqual(emitted[-1].state, BitrixHistoryR0HandoffState.CLOSED)
                self.assertNotIn("protected detail", result.model_dump_json())

        handoff = waiting_handoff()
        started = asyncio.Event()

        async def cancellable(_anchor):
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(
            execute_handoff_cli_session(
                settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                preflight_timeout_seconds=4,
                authorization_wait_seconds=5,
                armed_hold_seconds=5,
                confirmation_reader=lambda: asyncio.sleep(
                    0,
                    result=HISTORY_R0_ARM_CONFIRMATION,
                ),
                prepare_handoff=lambda **_kwargs: asyncio.sleep(0, result=handoff),
                armed_stage=cancellable,
                emit=lambda _snapshot: None,
            )
        )
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(handoff.snapshot().anchor_available)

    def test_wrong_first_confirmation_stops_before_settings(self):
        calls = []
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(
                    ["--confirm-code", "incorrecta"],
                    settings_loader=lambda: calls.append("settings"),
                )
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(calls, [])

    def test_main_remains_terminal_after_injected_reader_result(self):
        emitted = []
        exit_code = main(
            [
                "--confirm-code",
                HISTORY_R0_PREFLIGHT_CONFIRMATION,
                "--preflight-timeout-seconds",
                "4",
                "--authorization-wait-seconds",
                "5",
                "--armed-hold-seconds",
                "5",
            ],
            settings_loader=lambda: load_settings({"NIA_BITRIX_MODE": "off"}),
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            prepare_handoff=lambda **_kwargs: asyncio.sleep(
                0,
                result=waiting_handoff(),
            ),
            armed_stage=lambda _anchor: asyncio.sleep(0, result=reader_result()),
            emit=emitted.append,
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(emitted[-1].state, BitrixHistoryR0HandoffState.CLOSED)

    def test_main_cancellation_is_redacted_and_returns_130(self):
        emitted = []
        handoff = waiting_handoff()

        async def cancel_confirmation():
            raise asyncio.CancelledError

        exit_code = main(
            ["--confirm-code", HISTORY_R0_PREFLIGHT_CONFIRMATION],
            settings_loader=lambda: load_settings({"NIA_BITRIX_MODE": "off"}),
            confirmation_reader=cancel_confirmation,
            prepare_handoff=lambda **_kwargs: asyncio.sleep(
                0,
                result=handoff,
            ),
            armed_stage=lambda _anchor: asyncio.sleep(0, result=reader_result()),
            emit=emitted.append,
        )
        self.assertEqual(exit_code, 130)
        self.assertEqual(
            emitted[-1].reason,
            "bitrix_history_handoff_cli_cancelled",
        )
        self.assertFalse(emitted[-1].anchor_available)
        self.assertFalse(handoff.snapshot().anchor_available)

    def test_source_has_no_env_oauth_history_persistence_or_mutation(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_handoff_cli.py"
        ).read_text(encoding="utf-8")
        self.assertIn(HISTORY_R0_ARM_CONFIRMATION, source)
        for forbidden in (
            "load_dotenv",
            "dotenv",
            ".env",
            "os.environ",
            "get_access_token",
            "refresh_access_token",
            "get_session_history",
            "imopenlines.session.history.get",
            "config.update",
            "event.bind",
            "im.v2.Event.subscribe",
            "insert_one",
            "update_one",
            "asyncio.to_thread",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
