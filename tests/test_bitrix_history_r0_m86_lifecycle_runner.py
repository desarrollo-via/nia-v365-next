import asyncio
import unittest
from dataclasses import dataclass
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m85_final_command_rehearsal import (
    M85_FIRST_CONFIRMATION_TEXT,
    M85_MANUAL_REMOVAL_TEXT,
    M85_SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_m86_cross_turn_channel import (
    InMemoryM86AllowlistedStateBackend,
    M86ChannelAction,
    M86ChannelRecord,
    M86ChannelStage,
    M86CrossTurnChannel,
)
from bitrix_connector.bitrix_history_r0_m86_lifecycle_runner import (
    M86LifecycleRunner,
    build_real_m86_lifecycle_runner,
)
from bitrix_connector.bitrix_history_r0_m86_source_bound_command import (
    M86SourceBoundCommand,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PreflightSnapshot:
    state: str = "VERIFIED"
    combined_preflight_verified: bool = True
    history_anchor_available: bool = True
    private_resources_closed: bool = True
    bot_read_calls: int = 2
    openline_read_calls: int = 1
    history_dialog_read_calls: int = 1
    history_read_calls: int = 0
    oauth_refresh_calls: int = 0
    messages_sent: int = 0
    deletions_executed: int = 0
    connector_locked_off: bool = True
    persisted: bool = False
    nia_next_called: bool = False
    bitrix_written: bool = False


class OutcomeFixture:
    def require_anchor(self):
        return object()


class PreflightFixture:
    def __init__(self):
        self.outcome = OutcomeFixture()
        self.run_calls = 0
        self.take_calls = 0
        self.clear_calls = 0

    async def run_once(self):
        self.run_calls += 1
        return PreflightSnapshot()

    def take_history_outcome_once(self):
        self.take_calls += 1
        return self.outcome

    def clear(self):
        self.clear_calls += 1


class DeleteFailingBackend(InMemoryM86AllowlistedStateBackend):
    def delete(self, *, expected_sequence):
        self.delete_calls += 1
        raise RuntimeError("fixture_delete_failed")


@dataclass(frozen=True)
class RoundtripResult:
    state: str


class Harness:
    def __init__(
        self,
        *,
        result_state="VERIFIED",
        fail_event=None,
        cancel_read=False,
        backend=None,
    ):
        self.backend = backend or InMemoryM86AllowlistedStateBackend()
        self.preflight = PreflightFixture()
        self.events = []
        self.result_state = result_state
        self.fail_event = fail_event
        self.cancel_read = cancel_read
        self.control_calls = 0
        self.sleep_calls = 0
        self.roundtrip_calls = 0
        self.received_outcome = None

    def channel(self):
        return M86CrossTurnChannel(
            backend=self.backend,
            clock=lambda: 1000.0,
            execution_enabled=True,
        )

    def preflight_factory(self):
        return self.preflight

    def command(self, *, enabled=True):
        return M86SourceBoundCommand(
            preflight_owner_factory=self.preflight_factory,
            channel_factory=self.channel,
            execution_enabled=enabled,
        )

    async def control_reader(self):
        self.control_calls += 1
        if self.cancel_read:
            raise asyncio.CancelledError()
        return self.backend.load()

    async def sleeper(self, _seconds):
        self.sleep_calls += 1
        if self.sleep_calls == 1:
            self.channel().advance_once(
                action=M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
                literal=M85_MANUAL_REMOVAL_TEXT,
            )
        elif self.sleep_calls == 2:
            self.channel().advance_once(
                action=M86ChannelAction.CONFIRM_SECOND_EXECUTION,
                literal=M85_SECOND_CONFIRMATION_TEXT,
            )

    async def slow_sleeper(self, _seconds):
        self.sleep_calls += 1
        await asyncio.sleep(1)

    async def event_sink(self, event):
        self.events.append(event)
        if event.state == self.fail_event:
            raise RuntimeError("fixture_event_sink_failed")

    async def roundtrip(self, outcome):
        self.roundtrip_calls += 1
        self.received_outcome = outcome
        return RoundtripResult(self.result_state)

    def runner(self, *, enabled=True, sleeper=None, lifetime=300.0):
        return M86LifecycleRunner(
            command=self.command(enabled=enabled),
            control_reader=self.control_reader,
            channel_factory=self.channel,
            event_sink=self.event_sink,
            roundtrip_continuation=self.roundtrip,
            sleeper=sleeper or self.sleeper,
            execution_enabled=enabled,
            lifetime_seconds=lifetime,
            poll_seconds=0.01,
        )


class M86LifecycleRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_lifecycle_keeps_same_outcome_and_emits_attention_once(self):
        harness = Harness()
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertTrue(snapshot.preflight_ready)
        self.assertTrue(snapshot.manual_removal_confirmed)
        self.assertTrue(snapshot.second_confirmation_confirmed)
        self.assertTrue(snapshot.attention_boundary_reached)
        self.assertTrue(snapshot.same_private_outcome_handed_off)
        self.assertTrue(snapshot.waiting_state_consumed)
        self.assertTrue(snapshot.command_close_verified)
        self.assertFalse(snapshot.private_anchor_persisted)
        self.assertFalse(snapshot.private_anchor_exposed)
        self.assertEqual((snapshot.control_read_calls, snapshot.sleep_calls), (3, 2))
        self.assertEqual(snapshot.public_event_calls, 4)
        self.assertEqual(snapshot.roundtrip_calls, 1)
        self.assertIs(harness.received_outcome, harness.preflight.outcome)
        self.assertEqual(
            [event.state for event in harness.events],
            [
                "PREFLIGHT-READY",
                "MANUAL-REMOVAL-CONFIRMED",
                "SECOND-CONFIRMATION-CONFIRMED",
                "ATTENTION-REQUIRED",
            ],
        )
        attention = [event for event in harness.events if event.attention_required_now]
        self.assertEqual(len(attention), 1)
        self.assertTrue(attention[0].human_message_required_now)
        self.assertIsNone(harness.backend.record)

    async def test_verified_rollback_is_terminal_and_channel_is_cleared(self):
        harness = Harness(result_state="ROLLED-BACK")
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "ROLLED-BACK")
        self.assertEqual(snapshot.reason, "m86g_lifecycle_rolled_back")
        self.assertTrue(snapshot.waiting_state_consumed)
        self.assertIsNone(harness.backend.record)

    async def test_preview_and_disabled_runner_construct_no_lifecycle_resources(self):
        harness = Harness()
        value = harness.runner(enabled=False)

        preview = await value.run_once()
        blocked = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(blocked.reason, "m86g_execution_not_enabled")
        self.assertEqual((harness.preflight.run_calls, harness.control_calls), (0, 0))
        self.assertIsNone(harness.backend.record)

    async def test_wrong_first_confirmation_stops_before_preflight_and_cleans(self):
        harness = Harness()
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT + " ",
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertFalse(snapshot.preflight_ready)
        self.assertEqual((harness.preflight.run_calls, harness.control_calls), (0, 0))
        self.assertTrue(snapshot.command_close_verified)
        self.assertIsNone(harness.backend.record)

    async def test_timeout_cancels_wait_and_aborts_allowlisted_state(self):
        harness = Harness()
        snapshot = await harness.runner(
            sleeper=harness.slow_sleeper,
            lifetime=0.01,
        ).run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "TIMED-OUT")
        self.assertEqual(snapshot.retry_budget, 0)
        self.assertTrue(snapshot.preflight_ready)
        self.assertTrue(snapshot.command_close_verified)
        self.assertIsNone(harness.backend.record)
        self.assertEqual(harness.roundtrip_calls, 0)

    async def test_cancellation_from_control_is_terminal_and_cleans(self):
        harness = Harness(cancel_read=True)
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertTrue(snapshot.command_close_verified)
        self.assertIsNone(harness.backend.record)
        self.assertEqual(harness.roundtrip_calls, 0)

    async def test_event_sink_failure_prevents_roundtrip_and_cleans(self):
        harness = Harness(fail_event="ATTENTION-REQUIRED")
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(harness.roundtrip_calls, 0)
        self.assertTrue(snapshot.command_close_verified)
        self.assertIsNone(harness.backend.record)

    async def test_invalid_roundtrip_result_is_no_go_and_cleans_waiting_state(self):
        harness = Harness(result_state="UNKNOWN")
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.roundtrip_calls, 1)
        self.assertFalse(snapshot.waiting_state_consumed)
        self.assertTrue(snapshot.command_close_verified)
        self.assertIsNone(harness.backend.record)

    async def test_cleanup_failure_is_visible_and_cannot_report_verified(self):
        harness = Harness(backend=DeleteFailingBackend())
        snapshot = await harness.runner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "m86g_terminal_cleanup_failed")
        self.assertFalse(snapshot.command_close_verified)
        self.assertGreaterEqual(harness.backend.delete_calls, 2)

    async def test_runner_reuse_cannot_repeat_preflight(self):
        harness = Harness()
        value = harness.runner()
        first = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )
        second = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(first.state, "VERIFIED")
        self.assertEqual(second.reason, "m86g_runner_reuse_rejected")
        self.assertEqual(harness.preflight.run_calls, 1)

    async def test_real_builder_preview_is_inert_and_creates_no_runtime(self):
        runtime = ROOT / ".runtime"
        before = runtime.exists()
        value = build_real_m86_lifecycle_runner()

        preview = await value.run_once()

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(preview.remaining_real_bindings, 2)
        self.assertFalse(preview.command_available)
        self.assertEqual(runtime.exists(), before)

    def test_repr_and_source_have_no_process_service_or_notification_side_effect(self):
        harness = Harness()
        self.assertEqual(repr(harness.runner()), "M86LifecycleRunner(<redacted>)")
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_lifecycle_runner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "subprocess",
            "create_subprocess",
            "start-process",
            "input(",
            "argparse",
            "socket",
            "mocktransport",
            "lanzar_notificacion_codex",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
