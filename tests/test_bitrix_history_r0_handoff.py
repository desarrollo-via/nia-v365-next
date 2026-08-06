import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_handoff import (
    BitrixHistoryR0HandoffDecision,
    BitrixHistoryR0HandoffState,
    prepare_stored_oauth_history_handoff_once,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]


def outcome(*, ready=True, resources_closed=True):
    result = BitrixHistoryR0Result(
        status=(
            BitrixHistoryR0Status.READY
            if ready
            else BitrixHistoryR0Status.NO_GO
        ),
        reason=(
            "bitrix_history_preflight_ready"
            if ready
            else "bitrix_history_barrier_degraded"
        ),
        dialog_read_calls=1 if ready else 0,
        history_read_calls=0,
        dialog_verified=ready,
        session_verified=ready,
        baseline_captured=ready,
        resources_closed=resources_closed,
    )
    anchor = (
        BitrixHistoryR0Anchor(session_id=900, baseline_last_message_id=700)
        if ready
        else None
    )
    return BitrixHistoryR0PreflightOutcome(result, anchor)


class BitrixHistoryR0HandoffTests(unittest.IsolatedAsyncioTestCase):
    async def prepare(self, selected_outcome=None, *, error=None):
        calls = []

        async def execute_preflight(**kwargs):
            calls.append(kwargs)
            if error is not None:
                raise error
            return selected_outcome or outcome()

        settings = load_settings({"NIA_BITRIX_MODE": "off"})
        handoff = await prepare_stored_oauth_history_handoff_once(
            settings=settings,
            timeout_seconds=4.5,
            execute_preflight=execute_preflight,
        )
        return handoff, calls, settings

    async def test_ready_retains_only_private_redacted_anchor_and_waits(self):
        handoff, calls, settings = await self.prepare()
        snapshot = handoff.snapshot()

        self.assertEqual(calls, [{"settings": settings, "timeout_seconds": 4.5}])
        self.assertEqual(
            snapshot.state,
            BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
        )
        self.assertTrue(snapshot.preflight_ready)
        self.assertTrue(snapshot.anchor_available)
        self.assertFalse(snapshot.history_armed)
        self.assertEqual(snapshot.dialog_read_calls, 1)
        self.assertEqual(snapshot.history_read_calls, 0)
        self.assertEqual(snapshot.mutation_calls, 0)
        self.assertTrue(snapshot.resources_closed)
        serialized = snapshot.model_dump_json()
        for forbidden in ("900", "700", "session_id", "last_message_id"):
            self.assertNotIn(forbidden, serialized)
            self.assertNotIn(forbidden, repr(handoff))

    async def test_arm_keeps_anchor_but_never_reads_history(self):
        handoff, _calls, _settings = await self.prepare()
        gate_calls = 0

        async def gate():
            nonlocal gate_calls
            gate_calls += 1
            return BitrixHistoryR0HandoffDecision.ARM

        snapshot = await handoff.wait_for_authorization(
            authorization_gate=gate,
            timeout_seconds=5,
        )

        self.assertEqual(gate_calls, 1)
        self.assertEqual(snapshot.state, BitrixHistoryR0HandoffState.ARMED)
        self.assertTrue(snapshot.anchor_available)
        self.assertTrue(snapshot.history_armed)
        self.assertEqual(snapshot.history_read_calls, 0)
        self.assertEqual(snapshot.mutation_calls, 0)
        repeated = await handoff.wait_for_authorization(
            authorization_gate=lambda: gate(),
            timeout_seconds=5,
        )
        self.assertEqual(repeated, snapshot)
        self.assertEqual(gate_calls, 1)

    async def test_armed_reader_receives_anchor_once_and_it_is_always_discarded(self):
        handoff, _calls, _settings = await self.prepare()
        await handoff.wait_for_authorization(
            authorization_gate=lambda: asyncio.sleep(
                0,
                result=BitrixHistoryR0HandoffDecision.ARM,
            ),
            timeout_seconds=5,
        )
        received = []

        async def reader(anchor):
            received.append((anchor.session_id, anchor.baseline_last_message_id))
            return BitrixHistoryR0Result(
                status=BitrixHistoryR0Status.NO_GO,
                reason="bitrix_history_wait_timeout",
                dialog_read_calls=36,
                history_read_calls=0,
                baseline_captured=True,
                resources_closed=True,
            )

        result = await handoff.run_armed_reader_once(reader)
        self.assertEqual(result.reason, "bitrix_history_wait_timeout")
        self.assertEqual(received, [(900, 700)])
        self.assertFalse(handoff.snapshot().anchor_available)
        with self.assertRaisesRegex(RuntimeError, "bitrix_history_handoff_not_armed"):
            await handoff.run_armed_reader_once(reader)
        self.assertEqual(received, [(900, 700)])

    async def test_armed_reader_failure_and_cancellation_discard_anchor(self):
        async def arm(handoff):
            await handoff.wait_for_authorization(
                authorization_gate=lambda: asyncio.sleep(
                    0,
                    result=BitrixHistoryR0HandoffDecision.ARM,
                ),
                timeout_seconds=5,
            )

        failed, _calls, _settings = await self.prepare()
        await arm(failed)

        async def fail(_anchor):
            raise RuntimeError("protected detail")

        with self.assertRaisesRegex(RuntimeError, "protected detail"):
            await failed.run_armed_reader_once(fail)
        self.assertFalse(failed.snapshot().anchor_available)

        cancelled, _calls, _settings = await self.prepare()
        await arm(cancelled)

        async def cancel(_anchor):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await cancelled.run_armed_reader_once(cancel)
        self.assertEqual(cancelled.snapshot().state, BitrixHistoryR0HandoffState.CLOSED)
        self.assertFalse(cancelled.snapshot().anchor_available)

    async def test_cancel_and_close_discard_anchor_idempotently(self):
        handoff, _calls, _settings = await self.prepare()

        async def cancel_gate():
            return BitrixHistoryR0HandoffDecision.CANCEL

        cancelled = await handoff.wait_for_authorization(
            authorization_gate=cancel_gate,
            timeout_seconds=5,
        )
        self.assertEqual(cancelled.state, BitrixHistoryR0HandoffState.CANCELLED)
        self.assertFalse(cancelled.anchor_available)
        self.assertFalse(cancelled.history_armed)

        closed = await handoff.close()
        self.assertEqual(closed.state, BitrixHistoryR0HandoffState.CLOSED)
        self.assertFalse(closed.anchor_available)
        self.assertEqual(await handoff.close(), closed)

    async def test_no_go_or_failed_preflight_never_retains_anchor(self):
        cases = (
            (outcome(ready=False), None, "bitrix_history_barrier_degraded"),
            (
                outcome(resources_closed=False),
                None,
                "bitrix_history_resources_close_failed",
            ),
            (None, RuntimeError("protected detail"), "bitrix_history_handoff_preflight_failed_safe"),
        )
        for selected, error, reason in cases:
            with self.subTest(reason=reason):
                handoff, _calls, _settings = await self.prepare(
                    selected,
                    error=error,
                )
                snapshot = handoff.snapshot()
                self.assertEqual(snapshot.state, BitrixHistoryR0HandoffState.NO_GO)
                self.assertEqual(snapshot.reason, reason)
                self.assertFalse(snapshot.anchor_available)
                self.assertFalse(snapshot.history_armed)
                self.assertNotIn("protected detail", repr(handoff))

    async def test_timeout_invalid_decision_or_gate_failure_fails_closed(self):
        async def timeout_gate():
            await asyncio.Event().wait()
            return BitrixHistoryR0HandoffDecision.ARM

        async def invalid_gate():
            return "INVALID"

        async def failed_gate():
            raise RuntimeError("authorization secret")

        cases = (
            (timeout_gate, 0.001, "bitrix_history_handoff_authorization_timeout"),
            (invalid_gate, 5, "bitrix_history_handoff_decision_invalid"),
            (failed_gate, 5, "bitrix_history_handoff_authorization_failed_safe"),
        )
        for gate, timeout_seconds, reason in cases:
            with self.subTest(reason=reason):
                handoff, _calls, _settings = await self.prepare()
                snapshot = await handoff.wait_for_authorization(
                    authorization_gate=gate,
                    timeout_seconds=timeout_seconds,
                )
                self.assertEqual(snapshot.state, BitrixHistoryR0HandoffState.NO_GO)
                self.assertEqual(snapshot.reason, reason)
                self.assertFalse(snapshot.anchor_available)
                self.assertFalse(snapshot.history_armed)
                self.assertNotIn("secret", snapshot.model_dump_json())

        handoff, _calls, _settings = await self.prepare()
        invalid_timeout = await handoff.wait_for_authorization(
            authorization_gate=invalid_gate,
            timeout_seconds=301,
        )
        self.assertEqual(
            invalid_timeout.reason,
            "bitrix_history_handoff_timeout_invalid",
        )
        self.assertFalse(invalid_timeout.anchor_available)

    async def test_task_cancellation_and_context_exit_clear_anchor(self):
        handoff, _calls, _settings = await self.prepare()
        started = asyncio.Event()

        async def gate():
            started.set()
            await asyncio.Event().wait()
            return BitrixHistoryR0HandoffDecision.ARM

        task = asyncio.create_task(
            handoff.wait_for_authorization(
                authorization_gate=gate,
                timeout_seconds=5,
            )
        )
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        snapshot = handoff.snapshot()
        self.assertEqual(snapshot.state, BitrixHistoryR0HandoffState.CLOSED)
        self.assertFalse(snapshot.anchor_available)

        other, _calls, _settings = await self.prepare()
        async with other:
            self.assertTrue(other.snapshot().anchor_available)
        self.assertFalse(other.snapshot().anchor_available)

    async def test_source_has_no_env_oauth_history_persistence_or_mutation(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_handoff.py"
        ).read_text(encoding="utf-8")
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
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("def require_anchor", source)
        self.assertNotIn("def get_anchor", source)


if __name__ == "__main__":
    unittest.main()
