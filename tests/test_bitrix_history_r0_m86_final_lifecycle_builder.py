import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m85_final_command_rehearsal import (
    M85_FIRST_CONFIRMATION_TEXT,
    M85_MANUAL_REMOVAL_TEXT,
    M85_SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_m86_cross_turn_channel import (
    InMemoryM86AllowlistedStateBackend,
    M86ChannelAction,
    M86CrossTurnChannel,
)
from bitrix_connector.bitrix_history_r0_m86_final_lifecycle_builder import (
    M86AllowlistedLifecycleSurface,
    M86FinalLifecycleOwner,
    build_real_m86_final_lifecycle_owner,
    build_real_m86_lifecycle_surface,
)
from tests.test_bitrix_history_r0_m86_concrete_lifecycle_operations import (
    CredentialBackend,
    HermeticHttpFactory,
    OAuthBackend,
)


ROOT = Path(__file__).resolve().parents[1]


class Harness:
    def __init__(self, *, rollback=False, auto_confirm=True):
        self.credential = CredentialBackend()
        self.oauth = OAuthBackend()
        self.http = HermeticHttpFactory(rollback=rollback)
        self.backend = InMemoryM86AllowlistedStateBackend()
        self.events = []
        self.sleep_calls = 0
        self.message_wait_calls = 0
        self.requests_at_attention = None
        self.requests_at_message_ready = None
        self.auto_confirm = auto_confirm
        self.surface = M86AllowlistedLifecycleSurface(
            control_reader=self.control_reader,
            channel_factory=self.channel,
            sleeper=asyncio.sleep,
            poll_seconds=0.01,
            observer=self.event_sink,
        )

    def channel(self):
        return M86CrossTurnChannel(
            backend=self.backend,
            clock=lambda: 1000.0,
            execution_enabled=True,
        )

    async def control_reader(self):
        return self.backend.load()

    async def sleeper(self, _seconds):
        self.sleep_calls += 1
        if self.sleep_calls == 1:
            result = self.channel().advance_once(
                action=M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
                literal=M85_MANUAL_REMOVAL_TEXT,
            )
        else:
            result = self.channel().advance_once(
                action=M86ChannelAction.CONFIRM_SECOND_EXECUTION,
                literal=M85_SECOND_CONFIRMATION_TEXT,
            )
        if result.state != "ADVANCED":
            raise AssertionError("fixture transition failed")

    async def event_sink(self, event):
        self.events.append(event)
        if event.attention_required_now:
            self.requests_at_attention = len(self.http.requests)
            if self.auto_confirm:
                self.message_wait_calls += 1
                self.requests_at_message_ready = len(self.http.requests)
                signaled = self.surface.confirm_message_sent_once()
                if not signaled.message_sent_confirmed:
                    raise AssertionError("fixture message signal failed")

    def owner(self, *, enabled=True):
        return M86FinalLifecycleOwner(
            credential_backend=self.credential,
            oauth_backend=self.oauth,
            nia_base_url="https://nia.fixture.invalid",
            http_client_factory=self.http,
            control_reader=self.control_reader,
            channel_factory=self.channel,
            expected_sender_id=51,
            status_surface=self.surface,
            sleeper=self.sleeper,
            poll_seconds=0.01,
            execution_enabled=enabled,
        )


class M86FinalLifecycleBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_builder_spans_preflight_attention_ack_and_verified_m88(self):
        harness = Harness()
        value = harness.owner()

        snapshot = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertEqual(snapshot.protected_failure_category, "none")
        self.assertTrue(snapshot.first_confirmation_exact)
        self.assertTrue(snapshot.protected_scope_bound)
        self.assertTrue(snapshot.concrete_operations_bound)
        self.assertTrue(snapshot.cross_turn_wait_bound)
        self.assertTrue(snapshot.public_status_surface_bound)
        self.assertTrue(snapshot.launch_surface_available)
        self.assertTrue(snapshot.status_surface_available)
        self.assertTrue(snapshot.message_signal_surface_available)
        self.assertEqual(
            snapshot.sender_scope_mode,
            "controlled_chat_exact_unique_message",
        )
        self.assertFalse(snapshot.expected_sender_id_required)
        self.assertEqual(
            (snapshot.preflight_calls, snapshot.cross_turn_calls, snapshot.m88_calls),
            (1, 1, 1),
        )
        self.assertEqual(snapshot.public_event_calls, 4)
        self.assertEqual(snapshot.attention_event_calls, 1)
        self.assertEqual(snapshot.message_ready_wait_calls, 1)
        self.assertEqual(harness.message_wait_calls, 1)
        self.assertEqual(harness.requests_at_attention, 4)
        self.assertEqual(harness.requests_at_message_ready, 4)
        self.assertEqual(len(harness.http.requests), 8)
        self.assertEqual(
            sum(
                path == "/rest/imopenlines.dialog.get"
                for _, path, _ in harness.http.requests
            ),
            1,
        )
        self.assertEqual(
            [event.state for event in harness.events],
            [
                "PREFLIGHT-READY",
                "MANUAL-REMOVAL-CONFIRMED",
                "SECOND-CONFIRMATION-CONFIRMED",
                "ATTENTION-REQUIRED",
            ],
        )
        self.assertTrue(snapshot.channel_cleanup_verified)
        self.assertIsNone(harness.backend.record)
        self.assertEqual((snapshot.oauth_load_calls, snapshot.oauth_refresh_calls), (1, 0))
        self.assertTrue(snapshot.same_oauth_view_used)
        self.assertTrue(snapshot.private_resources_closed)
        self.assertTrue(all(client.is_closed for client in harness.http.clients))
        self.assertTrue(value.status().message_sent_confirmed)

    async def test_rollback_is_terminal_and_cleans_waiting_state(self):
        harness = Harness(rollback=True)

        snapshot = await harness.owner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "ROLLED-BACK")
        self.assertEqual(snapshot.protected_failure_category, "none")
        self.assertEqual(len(harness.http.requests), 10)
        self.assertEqual(snapshot.attention_event_calls, 1)
        self.assertTrue(snapshot.channel_cleanup_verified)
        self.assertIsNone(harness.backend.record)

    async def test_public_surface_pauses_before_m88_until_explicit_signal(self):
        harness = Harness(auto_confirm=False)
        value = harness.owner()
        task = asyncio.create_task(
            value.run_once(
                execute=True,
                first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
            )
        )
        for _ in range(100):
            if value.status().state == "ATTENTION-REQUIRED":
                break
            await asyncio.sleep(0)

        self.assertEqual(value.status().state, "ATTENTION-REQUIRED")
        self.assertTrue(value.status().attention_required_now)
        self.assertEqual(len(harness.http.requests), 4)
        self.assertFalse(task.done())

        signal = value.confirm_message_sent_once()
        snapshot = await task

        self.assertTrue(signal.message_sent_confirmed)
        self.assertEqual(snapshot.state, "VERIFIED")
        self.assertEqual(len(harness.http.requests), 8)

    async def test_wrong_confirmation_stops_before_source_oauth_http_or_attention(self):
        harness = Harness()

        snapshot = await harness.owner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT + " ",
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.protected_failure_category, "none")
        self.assertEqual(snapshot.reason, "m86j_first_confirmation_invalid")
        self.assertEqual((harness.credential.fetch_calls, harness.oauth.load_calls), (0, 0))
        self.assertEqual((harness.http.calls, harness.events), ([], []))
        self.assertIsNone(harness.backend.record)

    async def test_protected_source_failure_reaches_final_public_snapshot(self):
        class FailingCredentialBackend(CredentialBackend):
            async def fetch_exact(self, _target_id):
                self.fetch_calls += 1
                raise RuntimeError("private-source-detail")

        harness = Harness()
        harness.credential = FailingCredentialBackend()

        snapshot = await harness.owner().run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(
            snapshot.protected_failure_category,
            "protected_source_open_failed",
        )
        self.assertNotIn("private-source-detail", repr(snapshot))
        self.assertEqual(harness.oauth.load_calls, 0)
        self.assertEqual(harness.http.calls, [])

    async def test_preview_is_inert_and_opens_nothing(self):
        harness = Harness()
        value = harness.owner(enabled=False)

        preview = await value.run_once()
        blocked = await value.run_once(
            execute=True,
            first_confirmation=M85_FIRST_CONFIRMATION_TEXT,
        )

        self.assertEqual(preview.state, "PREPARED")
        self.assertEqual(preview.remaining_real_bindings, 0)
        self.assertEqual(preview.first_confirmation_decision, "REQUEST")
        self.assertTrue(preview.first_confirmation_request_ready)
        self.assertTrue(preview.command_available)
        self.assertEqual(blocked.reason, "m86j_execution_not_enabled")
        self.assertEqual((harness.credential.fetch_calls, harness.oauth.load_calls), (0, 0))
        self.assertEqual((harness.http.calls, harness.events), ([], []))
        self.assertIsNone(harness.backend.record)

    async def test_real_builder_preview_does_not_create_runtime_or_open_resources(self):
        runtime = ROOT / ".runtime"
        before = runtime.exists()
        value = build_real_m86_final_lifecycle_owner(
            nia_base_url="https://nia.fixture.invalid",
        )
        credential = value._resources._credential_backend
        oauth = value._resources._oauth_backend

        snapshot = await value.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(runtime.exists(), before)
        self.assertEqual(value.status().state, "PREPARED")
        self.assertIsNone(credential._native._api)
        self.assertIsNone(oauth._resources)

    async def test_real_surface_builder_is_inert_and_separately_available(self):
        runtime = ROOT / ".runtime"
        before = runtime.exists()

        surface = build_real_m86_lifecycle_surface()

        self.assertEqual(surface.snapshot().state, "PREPARED")
        self.assertEqual(runtime.exists(), before)

    async def test_real_owner_can_be_explicitly_armed_without_opening_resources(self):
        runtime = ROOT / ".runtime"
        before = runtime.exists()

        value = build_real_m86_final_lifecycle_owner(
            nia_base_url="https://nia.fixture.invalid",
            execution_enabled=True,
        )

        self.assertTrue(value._execution_enabled)
        self.assertEqual(value.preview().state, "PREPARED")
        self.assertEqual(runtime.exists(), before)

    async def test_separate_surface_can_signal_and_refresh_shared_state(self):
        backend = InMemoryM86AllowlistedStateBackend()

        def channel():
            return M86CrossTurnChannel(
                backend=backend,
                clock=lambda: 1000.0,
                execution_enabled=True,
            )

        async def reader():
            return backend.load()

        channel().advance_once(action=M86ChannelAction.OPEN_AFTER_PREFLIGHT)
        channel().advance_once(
            action=M86ChannelAction.CONFIRM_MANUAL_REMOVAL,
            literal=M85_MANUAL_REMOVAL_TEXT,
        )
        channel().advance_once(
            action=M86ChannelAction.CONFIRM_SECOND_EXECUTION,
            literal=M85_SECOND_CONFIRMATION_TEXT,
        )
        channel().advance_once(action=M86ChannelAction.MARK_WAITING_MESSAGE)
        observer = M86AllowlistedLifecycleSurface(
            control_reader=reader,
            channel_factory=channel,
        )
        signaler = M86AllowlistedLifecycleSurface(
            control_reader=reader,
            channel_factory=channel,
        )

        waiting = await observer.refresh_status()
        signaled = signaler.confirm_message_sent_once()
        refreshed = await observer.refresh_status()

        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertTrue(signaled.message_sent_confirmed)
        self.assertEqual(refreshed.state, "MESSAGE-SENT-CONFIRMED")
        self.assertTrue(refreshed.message_sent_confirmed)

    def test_surface_rejects_signal_before_attention_and_exposes_no_payload(self):
        backend = InMemoryM86AllowlistedStateBackend()

        def channel():
            return M86CrossTurnChannel(
                backend=backend,
                clock=lambda: 1000.0,
                execution_enabled=True,
            )

        async def reader():
            return backend.load()

        surface = M86AllowlistedLifecycleSurface(
            control_reader=reader,
            channel_factory=channel,
        )

        initial = surface.snapshot()
        rejected = surface.confirm_message_sent_once()

        self.assertEqual(initial.state, "PREPARED")
        self.assertEqual(rejected.state, "NO-GO")
        self.assertFalse(rejected.message_sent_confirmed)
        self.assertFalse(rejected.attention_required_now)
        self.assertFalse(rejected.payload_retained)

    def test_repr_and_source_have_no_secret_service_or_test_transport(self):
        harness = Harness()
        self.assertEqual(repr(harness.owner()), "M86FinalLifecycleOwner(<redacted>)")
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_final_lifecycle_builder.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env",
            "dotenv",
            "os.environ",
            "mocktransport",
            "pymongo",
            "motor",
            "refresh_access_token(",
            "subprocess",
            "socket",
            "input(",
            "print(",
            "lanzar_notificacion_codex",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
