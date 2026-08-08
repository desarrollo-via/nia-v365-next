import json
import tempfile
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m85_final_command_rehearsal import (
    M85_MANUAL_REMOVAL_TEXT,
    M85_SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_m86_cross_turn_channel import (
    InMemoryM86AllowlistedStateBackend,
    JsonFileM86AllowlistedStateBackend,
    M86ChannelAction,
    M86ChannelRecord,
    M86ChannelStage,
    M86CrossTurnChannel,
    M86_CHANNEL_FILENAME,
    M86_CHANNEL_LOCK_FILENAME,
    M86_CHANNEL_SCHEMA,
    M86_CHANNEL_TEMP_FILENAME,
    build_real_m86_cross_turn_channel,
)


ROOT = Path(__file__).resolve().parents[1]


def channel(backend, now=1000.0):
    return M86CrossTurnChannel(
        backend=backend,
        clock=lambda: now,
        execution_enabled=True,
    )


def advance(backend, action, *, literal=None, now=1000.0, ttl=300.0):
    return channel(backend, now).advance_once(
        action=action,
        literal=literal,
        ttl_seconds=ttl,
    )


class M86CrossTurnChannelTests(unittest.TestCase):
    def test_exact_in_memory_sequence_reaches_attention_only_at_waiting_message(self):
        backend = InMemoryM86AllowlistedStateBackend()

        opened = advance(backend, M86ChannelAction.OPEN_AFTER_PREFLIGHT)
        manual = advance(
            backend,
            M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
            literal=M85_MANUAL_REMOVAL_TEXT,
        )
        second = advance(
            backend,
            M86ChannelAction.CONFIRM_SECOND_EXECUTION,
            literal=M85_SECOND_CONFIRMATION_TEXT,
        )
        waiting = advance(backend, M86ChannelAction.MARK_WAITING_MESSAGE)

        self.assertEqual(
            (
                opened.resulting_stage,
                manual.resulting_stage,
                second.resulting_stage,
                waiting.resulting_stage,
            ),
            (
                M86ChannelStage.AWAITING_MANUAL_REMOVAL,
                M86ChannelStage.AWAITING_SECOND_CONFIRMATION,
                M86ChannelStage.READY_FOR_WAITING_MESSAGE,
                M86ChannelStage.WAITING_MESSAGE,
            ),
        )
        self.assertEqual((opened.sequence, manual.sequence, second.sequence, waiting.sequence), (1, 2, 3, 4))
        self.assertFalse(opened.attention_required_now)
        self.assertFalse(manual.attention_required_now)
        self.assertFalse(second.attention_required_now)
        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertTrue(waiting.attention_required_now)
        self.assertTrue(waiting.human_message_required_now)
        self.assertFalse(waiting.attention_notification_emitted)
        self.assertTrue(manual.literal_verified_in_memory)
        self.assertTrue(second.literal_verified_in_memory)
        self.assertFalse(any(item.literal_persisted for item in (opened, manual, second, waiting)))

        consumed = advance(backend, M86ChannelAction.CONSUME_WAITING_MESSAGE)
        self.assertEqual(consumed.state, "CONSUMED")
        self.assertTrue(consumed.private_state_cleared)
        self.assertIsNone(backend.record)
        self.assertEqual((backend.load_calls, backend.save_calls, backend.delete_calls), (5, 4, 1))

    def test_file_backend_survives_new_instances_and_persists_only_allowlisted_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            opened = advance(
                JsonFileM86AllowlistedStateBackend(root=root),
                M86ChannelAction.OPEN_AFTER_PREFLIGHT,
            )
            manual = advance(
                JsonFileM86AllowlistedStateBackend(root=root),
                M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
                literal=M85_MANUAL_REMOVAL_TEXT,
            )
            second = advance(
                JsonFileM86AllowlistedStateBackend(root=root),
                M86ChannelAction.CONFIRM_SECOND_EXECUTION,
                literal=M85_SECOND_CONFIRMATION_TEXT,
            )
            waiting = advance(
                JsonFileM86AllowlistedStateBackend(root=root),
                M86ChannelAction.MARK_WAITING_MESSAGE,
            )

            self.assertEqual((opened.state, manual.state, second.state), ("ADVANCED",) * 3)
            self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
            state_path = root / M86_CHANNEL_FILENAME
            payload_text = state_path.read_text(encoding="utf-8")
            payload = json.loads(payload_text)
            self.assertEqual(
                set(payload),
                {"schema_name", "stage", "sequence", "expires_at_unix"},
            )
            self.assertEqual(payload["schema_name"], M86_CHANNEL_SCHEMA)
            self.assertEqual(payload["stage"], "WAITING-MESSAGE")
            self.assertNotIn(M85_MANUAL_REMOVAL_TEXT, payload_text)
            self.assertNotIn(M85_SECOND_CONFIRMATION_TEXT, payload_text)
            self.assertFalse((root / M86_CHANNEL_LOCK_FILENAME).exists())
            self.assertFalse((root / M86_CHANNEL_TEMP_FILENAME).exists())

            consumed = advance(
                JsonFileM86AllowlistedStateBackend(root=root),
                M86ChannelAction.CONSUME_WAITING_MESSAGE,
            )
            self.assertEqual(consumed.state, "CONSUMED")
            self.assertFalse(state_path.exists())

    def test_wrong_literal_is_terminal_and_deletes_existing_state(self):
        backend = InMemoryM86AllowlistedStateBackend()
        advance(backend, M86ChannelAction.OPEN_AFTER_PREFLIGHT)

        result = advance(
            backend,
            M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
            literal="wrong",
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.reason, "m86d_channel_failed_safe")
        self.assertTrue(result.private_state_cleared)
        self.assertFalse(result.literal_verified_in_memory)
        self.assertIsNone(backend.record)
        self.assertEqual((backend.save_calls, backend.delete_calls), (1, 1))

    def test_out_of_order_action_clears_channel_without_retry(self):
        backend = InMemoryM86AllowlistedStateBackend()
        advance(backend, M86ChannelAction.OPEN_AFTER_PREFLIGHT)

        result = advance(backend, M86ChannelAction.MARK_WAITING_MESSAGE)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.retry_budget, 0)
        self.assertTrue(result.private_state_cleared)
        self.assertIsNone(backend.record)

    def test_expired_record_is_deleted_before_requested_transition(self):
        backend = InMemoryM86AllowlistedStateBackend()
        advance(
            backend,
            M86ChannelAction.OPEN_AFTER_PREFLIGHT,
            now=1000.0,
            ttl=10.0,
        )

        result = advance(
            backend,
            M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
            literal=M85_MANUAL_REMOVAL_TEXT,
            now=1010.0,
        )

        self.assertEqual(result.state, "EXPIRED")
        self.assertTrue(result.expired_state_cleared)
        self.assertTrue(result.private_state_cleared)
        self.assertFalse(result.literal_verified_in_memory)
        self.assertIsNone(backend.record)

    def test_one_channel_instance_cannot_execute_two_actions(self):
        backend = InMemoryM86AllowlistedStateBackend()
        value = channel(backend)

        first = value.advance_once(action=M86ChannelAction.OPEN_AFTER_PREFLIGHT)
        second = value.advance_once(
            action=M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
            literal=M85_MANUAL_REMOVAL_TEXT,
        )

        self.assertEqual(first.state, "ADVANCED")
        self.assertEqual(second.reason, "m86d_channel_reuse_rejected")
        self.assertEqual((backend.load_calls, backend.save_calls), (1, 1))
        self.assertEqual(backend.record.stage, M86ChannelStage.AWAITING_MANUAL_REMOVAL)

    def test_sequence_conflict_is_fail_closed_and_cleared(self):
        backend = InMemoryM86AllowlistedStateBackend()
        backend.record = M86ChannelRecord(
            stage=M86ChannelStage.AWAITING_SECOND_CONFIRMATION,
            sequence=2,
            expires_at_unix=1200.0,
        )

        result = advance(
            backend,
            M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
            literal=M85_MANUAL_REMOVAL_TEXT,
        )

        self.assertEqual(result.state, "NO-GO")
        self.assertTrue(result.private_state_cleared)
        self.assertIsNone(backend.record)

    def test_malformed_file_is_removed_by_exact_fail_safe_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / M86_CHANNEL_FILENAME
            state_path.write_text('{"unexpected":"private"}', encoding="utf-8")
            backend = JsonFileM86AllowlistedStateBackend(root=root)

            result = advance(backend, M86ChannelAction.ABORT)

            self.assertEqual(result.state, "NO-GO")
            self.assertTrue(result.private_state_cleared)
            self.assertFalse(state_path.exists())

    def test_real_binding_preview_is_inert_and_does_not_create_runtime_state(self):
        value = build_real_m86_cross_turn_channel()
        backend = value._backend
        before = backend._root.exists()
        state_before = backend._state_path.exists()

        preview = value.preview()
        result = value.advance_once(action=M86ChannelAction.OPEN_AFTER_PREFLIGHT)

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(result.state, "PREPARED")
        self.assertEqual(result.action_calls, 0)
        self.assertEqual(result.remaining_real_bindings, 1)
        self.assertFalse(result.attention_required_now)
        self.assertFalse(result.human_message_required_now)
        self.assertEqual(backend._root.exists(), before)
        self.assertEqual(backend._state_path.exists(), state_before)

    def test_repr_and_source_expose_no_values_services_or_notification_call(self):
        memory = InMemoryM86AllowlistedStateBackend()
        value = channel(memory)
        self.assertEqual(repr(value), "M86CrossTurnChannel(<redacted>)")
        with tempfile.TemporaryDirectory() as directory:
            backend = JsonFileM86AllowlistedStateBackend(root=Path(directory))
            self.assertEqual(
                repr(backend),
                "JsonFileM86AllowlistedStateBackend(<redacted>)",
            )
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_cross_turn_channel.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "mocktransport",
            ".env",
            "dotenv",
            "os.environ",
            "pymongo",
            "motor",
            "httpx",
            "requests",
            "subprocess",
            "socket",
            "print(",
            "toast",
            "messagebox",
            "lanzar_notificacion",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
