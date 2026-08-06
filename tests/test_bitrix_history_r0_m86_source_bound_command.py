import asyncio
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m85_final_command_rehearsal import (
    M85_FIRST_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_m86_cross_turn_channel import (
    InMemoryM86AllowlistedStateBackend,
    M86ChannelStage,
    M86CrossTurnChannel,
)
from bitrix_connector.bitrix_history_r0_m86_source_bound_command import (
    M86E_COMMAND_NAME,
    M86SourceBoundCommand,
    build_real_m86_source_bound_command,
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
    def __init__(self, *, snapshot=None, cancel=False):
        self.snapshot = snapshot or PreflightSnapshot()
        self.cancel = cancel
        self.run_calls = 0
        self.take_calls = 0
        self.clear_calls = 0

    async def run_once(self):
        self.run_calls += 1
        if self.cancel:
            raise asyncio.CancelledError()
        return self.snapshot

    def take_history_outcome_once(self):
        self.take_calls += 1
        return OutcomeFixture()

    def clear(self):
        self.clear_calls += 1


class Factories:
    def __init__(self, *, preflight=None):
        self.preflight = preflight or PreflightFixture()
        self.backend = InMemoryM86AllowlistedStateBackend()
        self.preflight_calls = 0
        self.channel_calls = 0

    def build_preflight(self):
        self.preflight_calls += 1
        return self.preflight

    def build_channel(self):
        self.channel_calls += 1
        return M86CrossTurnChannel(
            backend=self.backend,
            clock=lambda: 1000.0,
            execution_enabled=True,
        )


def command(factories, *, enabled=True):
    return M86SourceBoundCommand(
        preflight_owner_factory=factories.build_preflight,
        channel_factory=factories.build_channel,
        execution_enabled=enabled,
    )


class M86SourceBoundCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_is_source_bound_but_inert_and_requests_no_attention(self):
        factories = Factories()
        value = command(factories)

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(snapshot.first_confirmation_decision, "REQUEST")
        self.assertTrue(snapshot.first_confirmation_request_ready)
        self.assertTrue(snapshot.source_bound)
        self.assertTrue(snapshot.command_available)
        self.assertEqual(snapshot.remaining_real_bindings, 0)
        self.assertFalse(snapshot.attention_required_now)
        self.assertFalse(snapshot.human_message_required_now)
        self.assertEqual((factories.preflight_calls, factories.channel_calls), (0, 0))

    async def test_disabled_real_shape_rejects_execution_before_literal_or_factories(self):
        factories = Factories()
        snapshot = await command(factories, enabled=False).run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.reason, "m86e_execution_not_enabled")
        self.assertFalse(snapshot.first_confirmation_consumed)
        self.assertEqual((factories.preflight_calls, factories.channel_calls), (0, 0))

    async def test_wrong_first_literal_is_terminal_before_source_preflight_or_channel(self):
        factories = Factories()
        snapshot = await command(factories).run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT + " ",
        )

        self.assertEqual(snapshot.reason, "m86e_first_confirmation_invalid")
        self.assertFalse(snapshot.first_confirmation_exact)
        self.assertFalse(snapshot.first_confirmation_consumed)
        self.assertEqual((factories.preflight_calls, factories.channel_calls), (0, 0))

    async def test_exact_first_confirmation_runs_preflight_opens_channel_and_retains_anchor(self):
        factories = Factories()
        value = command(factories)

        snapshot = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "PREFLIGHT-READY")
        self.assertTrue(snapshot.first_confirmation_exact)
        self.assertTrue(snapshot.first_confirmation_consumed)
        self.assertTrue(snapshot.combined_preflight_verified)
        self.assertEqual(snapshot.preflight_read_calls, 4)
        self.assertTrue(snapshot.private_anchor_retained)
        self.assertFalse(snapshot.private_anchor_persisted)
        self.assertEqual(snapshot.channel_stage, M86ChannelStage.AWAITING_MANUAL_REMOVAL)
        self.assertEqual((factories.preflight_calls, factories.preflight.run_calls), (1, 1))
        self.assertEqual((factories.channel_calls, factories.backend.save_calls), (1, 1))
        self.assertIsNotNone(value.take_private_history_outcome_once())
        with self.assertRaisesRegex(RuntimeError, "outcome_unavailable"):
            value.take_private_history_outcome_once()

    async def test_preflight_no_go_never_opens_channel_and_clears_private_owner(self):
        failed = PreflightFixture(
            snapshot=PreflightSnapshot(
                state="NO-GO",
                combined_preflight_verified=False,
                history_anchor_available=False,
            )
        )
        factories = Factories(preflight=failed)
        snapshot = await command(factories).run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertTrue(snapshot.first_confirmation_consumed)
        self.assertEqual(failed.clear_calls, 1)
        self.assertIsNone(factories.backend.record)
        self.assertEqual((factories.channel_calls, factories.backend.delete_calls), (0, 0))

    async def test_cancellation_is_terminal_and_cleans_without_retry(self):
        preflight = PreflightFixture(cancel=True)
        factories = Factories(preflight=preflight)
        snapshot = await command(factories).run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "CANCELLED")
        self.assertEqual(snapshot.retry_budget, 0)
        self.assertEqual(preflight.clear_calls, 1)
        self.assertIsNone(factories.backend.record)
        self.assertEqual(factories.channel_calls, 0)

    async def test_reuse_cannot_repeat_preflight_or_open_channel(self):
        factories = Factories()
        value = command(factories)
        await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )
        second = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(second.reason, "m86e_command_reuse_rejected")
        self.assertEqual((factories.preflight_calls, factories.channel_calls), (1, 1))

    async def test_close_aborts_allowlisted_channel_and_drops_private_anchor(self):
        factories = Factories()
        value = command(factories)
        await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        closed = await value.close()

        self.assertEqual(closed.state, "CLOSED")
        self.assertIsNone(factories.backend.record)
        with self.assertRaisesRegex(RuntimeError, "outcome_unavailable"):
            value.take_private_history_outcome_once()

    async def test_real_builder_preview_does_not_create_runtime_or_open_bindings(self):
        runtime = ROOT / ".runtime"
        before = runtime.exists()
        value = build_real_m86_source_bound_command()

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(snapshot.first_confirmation_decision, "REQUEST")
        self.assertEqual(snapshot.remaining_real_bindings, 0)
        self.assertEqual(runtime.exists(), before)
        self.assertIsNotNone(value._preflight_owner_factory)
        self.assertIsNone(value._preflight_owner)
        self.assertIsNone(value._history_outcome)

    def test_contract_repr_and_source_keep_command_non_cli_and_notification_free(self):
        factories = Factories()
        self.assertEqual(repr(command(factories)), "M86SourceBoundCommand(<redacted>)")
        self.assertEqual(M86E_COMMAND_NAME, "nia-next-r1-first-confirmation-preflight")
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_source_bound_command.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "mocktransport",
            "send_approved",
            "delete_approved",
            "lanzar_notificacion_codex",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
