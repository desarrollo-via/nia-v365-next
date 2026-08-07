import asyncio
import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
    compose_stored_oauth_history_armed_reader,
)
from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
    BitrixSessionHistory,
)
from bitrix_connector.bitrix_history_r0_handoff import (
    BitrixHistoryR0HandoffState,
    BitrixHistoryR0InMemoryHandoff,
)
from bitrix_connector.bitrix_history_r0_handoff_cli import (
    HISTORY_R0_ARM_CONFIRMATION,
    execute_handoff_cli_session,
)
from bitrix_connector.bitrix_history_r0_preflight import BitrixHistoryR0Anchor
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Status,
    BitrixHistoryR0WaitingMessageSnapshot,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
MESSAGE = "mensaje controlado único"
MESSAGE_HASH = hashlib.sha256(MESSAGE.encode("utf-8")).hexdigest()
WINDOW_START = datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)
TOKEN = "oauth-secret-token"


def dialog(last_message_id=701, session_id=900):
    return BitrixHistoryDialog.model_validate({
        "id": 78733,
        "dialog_id": "chat78733",
        "entity_type": "LINES",
        "entity_data_1": f"a|b|c|d|e|{session_id}",
        "role": "guest",
        "last_message_id": last_message_id,
    })


def history():
    return BitrixSessionHistory.model_validate({
        "chatId": 78733,
        "sessionId": 900,
        "message": [{
            "id": 701,
            "chatid": 78733,
            "senderid": 51,
            "recipientid": "chat78733",
            "date": "2026-07-31T15:00:01+00:00",
            "text": MESSAGE,
        }],
        "users": [{"id": 51, "connector": True}],
    })


class FakeProvider:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.refresh_calls = 0

    async def get_access_token(self, member_id):
        self.calls.append(member_id)
        if self.error is not None:
            raise self.error
        return TOKEN

    async def refresh_access_token(self, *_args):
        self.refresh_calls += 1
        raise AssertionError("refresh must not run")


class FakeResources:
    def __init__(self, provider=None, close_error=False):
        self.oauth_provider = provider or FakeProvider()
        self.portal_url = "https://portal.bitrix24.test"
        self.member_id = "member-protected"
        self.close_error = close_error
        self.closed = False

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("resource close secret")


class FakeFactory:
    def __init__(self, resources):
        self.resources = resources
        self.calls = []

    async def build(self, settings, *, timeout_seconds):
        self.calls.append((settings, timeout_seconds))
        return self.resources


class FakeClient:
    def __init__(self, dialogs=None, history_result=None, close_error=False):
        self.dialogs = list(dialogs or [])
        self.history_result = history_result
        self.close_error = close_error
        self.dialog_calls = 0
        self.history_calls = 0
        self.closed = False

    async def get_dialog(self, _dialog_id):
        self.dialog_calls += 1
        return BitrixHistoryReadResult(
            decision=BitrixHistoryReadDecision.SUCCESS,
            dialog=self.dialogs.pop(0),
            http_status=200,
        )

    async def get_session_history(self, _session_id):
        self.history_calls += 1
        return self.history_result

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("client close secret")


async def no_sleep(_seconds):
    return None


def inputs(**updates):
    values = {
        "expected_text_sha256": MESSAGE_HASH,
        "window_start": WINDOW_START,
        "wait_seconds": 10,
        "poll_seconds": 5,
    }
    values.update(updates)
    return BitrixHistoryR0EphemeralInputs(**values)


class BitrixHistoryR0ArmedCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_cli_composition_audit_is_ordered_inert_and_redacted(self):
        settings = load_settings({"NIA_BITRIX_MODE": "off"})
        handoff = BitrixHistoryR0InMemoryHandoff(
            state=BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
            reason="bitrix_history_handoff_waiting_authorization",
            anchor=BitrixHistoryR0Anchor(900, 700),
            preflight_ready=True,
            dialog_read_calls=1,
            resources_closed=True,
        )
        events = []
        emitted = []

        class TracedResources(FakeResources):
            async def close(self):
                events.append("resources-close")
                await super().close()

        class TracedClient(FakeClient):
            async def get_dialog(self, dialog_id):
                events.append("dialog-read")
                return await super().get_dialog(dialog_id)

            async def get_session_history(self, session_id):
                events.append("history-read")
                return await super().get_session_history(session_id)

            async def close(self):
                events.append("client-close")
                await super().close()

        resources = TracedResources()
        factory = FakeFactory(resources)
        client = TracedClient(
            dialogs=[dialog()],
            history_result=BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.SUCCESS,
                history=history(),
                http_status=200,
            ),
        )

        async def confirmation_reader():
            events.append("confirmation")
            return HISTORY_R0_ARM_CONFIRMATION

        async def expected_hash_reader():
            events.append("hidden-hash")
            return MESSAGE_HASH

        async def tracked_sleep(_seconds):
            events.append("poll-wait")

        def emit(output):
            state = getattr(output, "state", None)
            marker = getattr(state, "value", state)
            if marker is None:
                status = getattr(output, "status", None)
                marker = getattr(status, "value", status)
            events.append(f"emit:{marker}")
            emitted.append(output)

        def composer(**kwargs):
            events.append("compose")
            return compose_stored_oauth_history_armed_reader(
                **kwargs,
                resources_factory=factory,
                client_builder=lambda **_client_kwargs: client,
                sleep=tracked_sleep,
            )

        result = await execute_handoff_cli_session(
            settings=settings,
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=10,
            confirmation_reader=confirmation_reader,
            prepare_handoff=lambda **_kwargs: asyncio.sleep(0, result=handoff),
            emit=emit,
            expected_hash_reader=expected_hash_reader,
            armed_reader_composer=composer,
            utc_now=lambda: WINDOW_START,
        )

        self.assertEqual(result.status, BitrixHistoryR0Status.RECEIVED)
        self.assertEqual(
            [
                getattr(
                    getattr(item, "state", None),
                    "value",
                    getattr(item, "state", None),
                )
                or getattr(getattr(item, "status", None), "value", None)
                for item in emitted
            ],
            [
                "WAITING-AUTHORIZATION",
                "ARMED",
                "WAITING-MESSAGE",
                "RECEIVED",
                "CLOSED",
            ],
        )
        self.assertLess(events.index("emit:WAITING-MESSAGE"), events.index("poll-wait"))
        self.assertLess(events.index("poll-wait"), events.index("dialog-read"))
        self.assertLess(events.index("dialog-read"), events.index("history-read"))
        self.assertLess(events.index("history-read"), events.index("client-close"))
        self.assertLess(events.index("client-close"), events.index("resources-close"))
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(resources.oauth_provider.calls, [resources.member_id])
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(client.dialog_calls, 1)
        self.assertEqual(client.history_calls, 1)
        self.assertTrue(client.closed)
        self.assertTrue(resources.closed)
        self.assertFalse(handoff.snapshot().anchor_available)
        serialized = "".join(item.model_dump_json() for item in emitted)
        for forbidden in (
            MESSAGE,
            MESSAGE_HASH,
            TOKEN,
            resources.member_id,
            resources.portal_url,
            "session_id",
            "baseline_last_message_id",
            "expected_text_sha256",
            "access_token",
            "member_id",
        ):
            self.assertNotIn(forbidden, serialized)

    async def test_composed_reader_plugs_into_armed_cli_hook_with_doubles(self):
        settings = load_settings({"NIA_BITRIX_MODE": "off"})
        handoff = BitrixHistoryR0InMemoryHandoff(
            state=BitrixHistoryR0HandoffState.WAITING_AUTHORIZATION,
            reason="bitrix_history_handoff_waiting_authorization",
            anchor=BitrixHistoryR0Anchor(900, 700),
            preflight_ready=True,
            dialog_read_calls=1,
            resources_closed=True,
        )
        resources = FakeResources()
        client = FakeClient(
            dialogs=[dialog()],
            history_result=BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.SUCCESS,
                history=history(),
                http_status=200,
            ),
        )
        reader = compose_stored_oauth_history_armed_reader(
            settings=settings,
            inputs=inputs(),
            resources_factory=FakeFactory(resources),
            client_builder=lambda **_kwargs: client,
            sleep=no_sleep,
        )
        emitted = []

        result = await execute_handoff_cli_session(
            settings=settings,
            preflight_timeout_seconds=4,
            authorization_wait_seconds=5,
            armed_hold_seconds=10,
            confirmation_reader=lambda: asyncio.sleep(
                0,
                result=HISTORY_R0_ARM_CONFIRMATION,
            ),
            prepare_handoff=lambda **_kwargs: asyncio.sleep(0, result=handoff),
            armed_stage=reader,
            emit=emitted.append,
        )

        self.assertEqual(result.status, BitrixHistoryR0Status.RECEIVED)
        self.assertEqual(client.dialog_calls, 1)
        self.assertEqual(client.history_calls, 1)
        self.assertEqual(
            emitted[-1].state,
            BitrixHistoryR0HandoffState.CLOSED,
        )
        self.assertFalse(handoff.snapshot().anchor_available)

    async def test_composition_is_lazy_redacted_and_reads_once_when_invoked(self):
        resources = FakeResources()
        factory = FakeFactory(resources)
        client = FakeClient(
            dialogs=[dialog()],
            history_result=BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.SUCCESS,
                history=history(),
                http_status=200,
            ),
        )
        build_calls = []
        waiting = []

        async def on_waiting_message(snapshot):
            waiting.append(snapshot)
            self.assertEqual(client.dialog_calls, 0)
            self.assertFalse(client.closed)

        def client_builder(**kwargs):
            build_calls.append(kwargs)
            return client

        ephemeral = inputs()
        reader = compose_stored_oauth_history_armed_reader(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            inputs=ephemeral,
            resources_factory=factory,
            client_builder=client_builder,
            sleep=no_sleep,
            on_waiting_message=on_waiting_message,
        )

        self.assertEqual(factory.calls, [])
        self.assertNotIn(MESSAGE_HASH, repr(ephemeral))
        self.assertNotIn(MESSAGE_HASH, repr(reader))
        result = await reader(BitrixHistoryR0Anchor(900, 700))

        self.assertEqual(result.status, BitrixHistoryR0Status.RECEIVED)
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(resources.oauth_provider.calls, [resources.member_id])
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(build_calls, [{
            "portal_url": resources.portal_url,
            "access_token": TOKEN,
            "timeout_seconds": 10.0,
        }])
        self.assertEqual(client.dialog_calls, 1)
        self.assertEqual(client.history_calls, 1)
        self.assertEqual(len(waiting), 1)
        self.assertIsInstance(waiting[0], BitrixHistoryR0WaitingMessageSnapshot)
        self.assertTrue(client.closed)
        self.assertTrue(resources.closed)
        self.assertTrue(result.resources_closed)

    async def test_degraded_barrier_or_timeout_stops_before_resources(self):
        resources = FakeResources()
        factory = FakeFactory(resources)
        degraded = load_settings({
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_PILOT_ENABLED": "true",
            "NIA_BITRIX_PILOT_EMERGENCY_STOP": "false",
            "NIA_BITRIX_PILOT_RULES_JSON": "[]",
        })
        barrier_reader = compose_stored_oauth_history_armed_reader(
            settings=degraded,
            inputs=inputs(),
            resources_factory=factory,
        )
        timeout_reader = compose_stored_oauth_history_armed_reader(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            inputs=inputs(),
            timeout_seconds=10.1,
            resources_factory=factory,
        )

        barrier = await barrier_reader(BitrixHistoryR0Anchor(900, 700))
        timeout = await timeout_reader(BitrixHistoryR0Anchor(900, 700))
        self.assertEqual(barrier.reason, "bitrix_history_barrier_degraded")
        self.assertEqual(timeout.reason, "bitrix_history_timeout_invalid")
        self.assertEqual(factory.calls, [])

    def test_ephemeral_inputs_reject_hash_window_and_unbounded_wait(self):
        cases = (
            {"expected_text_sha256": "invalid"},
            {"window_start": datetime(2026, 7, 31, 15, 0)},
            {"wait_seconds": 301},
            {"poll_seconds": 4},
        )
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                inputs(**updates)

    async def test_token_or_builder_failure_closes_and_redacts(self):
        cases = (
            (FakeResources(FakeProvider(RuntimeError("token secret"))), None),
            (FakeResources(), RuntimeError("builder secret")),
        )
        for resources, builder_error in cases:
            with self.subTest(builder_error=builder_error is not None):
                def builder(**_kwargs):
                    if builder_error is not None:
                        raise builder_error
                    raise AssertionError("builder must not run")

                reader = compose_stored_oauth_history_armed_reader(
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                    inputs=inputs(),
                    resources_factory=FakeFactory(resources),
                    client_builder=builder,
                )
                result = await reader(BitrixHistoryR0Anchor(900, 700))
                self.assertEqual(
                    result.reason,
                    "bitrix_history_armed_reader_failed_safe",
                )
                self.assertTrue(result.resources_closed)
                self.assertTrue(resources.closed)
                self.assertNotIn("secret", result.model_dump_json())

    async def test_reader_is_one_shot_and_close_failure_is_terminal(self):
        resources = FakeResources()
        client = FakeClient(dialogs=[dialog()], close_error=True)
        reader = compose_stored_oauth_history_armed_reader(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            inputs=inputs(wait_seconds=5),
            resources_factory=FakeFactory(resources),
            client_builder=lambda **_kwargs: client,
            sleep=no_sleep,
        )
        first = await reader(BitrixHistoryR0Anchor(900, 700))
        second = await reader(BitrixHistoryR0Anchor(900, 700))
        self.assertEqual(first.reason, "bitrix_history_resources_close_failed")
        self.assertFalse(first.resources_closed)
        self.assertEqual(second.reason, "bitrix_history_armed_reader_already_used")
        self.assertEqual(client.dialog_calls, 1)
        self.assertTrue(resources.closed)

    async def test_cancellation_closes_and_source_has_no_mutation_surface(self):
        resources = FakeResources(FakeProvider(asyncio.CancelledError()))
        reader = compose_stored_oauth_history_armed_reader(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            inputs=inputs(),
            resources_factory=FakeFactory(resources),
        )
        with self.assertRaises(asyncio.CancelledError):
            await reader(BitrixHistoryR0Anchor(900, 700))
        self.assertTrue(resources.closed)

        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_armed_composition.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "load_dotenv",
            "dotenv",
            "os.environ",
            "refresh_access_token",
            "config.update",
            "event.bind",
            "im.v2.Event.subscribe",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
