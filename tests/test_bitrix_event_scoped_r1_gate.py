import unittest

from bitrix_connector.bitrix_event_scoped_r1_gate import (
    EVENT_R1_FIRST_CONFIRMATION,
    EVENT_R1_SECOND_CONFIRMATION,
    EventScopedR1Gate,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
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
from bitrix_connector.models import NormalizedBitrixEvent, WebhookReceipt


def settings():
    return load_settings(
        {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-123",
        }
    )


def event():
    return NormalizedBitrixEvent.model_validate(
        {
            "event": "ONIMBOTV2MESSAGEADD",
            "bot_id": 373259,
            "message_id": 9001,
            "chat_id": 78733,
            "dialog_id": "chat78733",
            "author_id": 27,
            "text": "fixture",
            "user_id": 27,
            "user_is_connector": True,
            "domain": "portal.bitrix24.test",
            "member_id": "member-123",
        }
    )


def receipt():
    return WebhookReceipt.model_validate(
        {
            "status": "disabled",
            "reason": "connector_locked_off",
            "effective_mode": "off",
            "event_key": "fixture",
            "identity_verified": True,
            "redacted_secret_fields": 2,
            "duplicate_detection": "not_persisted",
            "persisted": False,
            "nia_called": False,
            "bitrix_written": False,
            "event_summary": {
                "event": "ONIMBOTV2MESSAGEADD",
                "bot_id": 373259,
                "message_id": 9001,
                "chat_id": 78733,
                "dialog_id": "chat78733",
                "text_length": 7,
                "is_system": False,
            },
        }
    )


def outcome():
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.READY,
            reason="bitrix_history_preflight_ready",
            dialog_read_calls=1,
            history_read_calls=0,
            dialog_verified=True,
            session_verified=True,
            baseline_captured=True,
            resources_closed=True,
        ),
        BitrixHistoryR0Anchor(700, 9001),
    )


class Result:
    state = "VERIFIED"


class EventScopedR1GateTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_order_then_signals_attention_and_consumes_one_event(self):
        calls = []

        async def preflight(_settings, view):
            calls.append(("preflight", view.read_text()))
            return outcome()

        async def roundtrip(_settings, view, received, incoming):
            calls.append(
                ("roundtrip", view.read_text(), received.require_anchor().session_id, incoming.chat_id)
            )
            return Result()

        gate = EventScopedR1Gate(
            preflight=preflight, roundtrip=roundtrip, execution_enabled=True
        )
        self.assertEqual(
            gate.accept_first_confirmation_once(EVENT_R1_FIRST_CONFIRMATION).state,
            "AWAITING-SECOND-CONFIRMATION",
        )
        armed = gate.accept_second_confirmation_once(EVENT_R1_SECOND_CONFIRMATION)
        self.assertEqual(armed.state, "ATTENTION-REQUIRED")
        self.assertTrue(armed.attention_required_now)
        token = bytearray(b"event-fixture-token")
        view = StoredOAuthAccessView(token)
        await gate.observe(event(), receipt(), settings(), view)
        await gate.observe(event(), receipt(), settings(), view)
        view.close()
        token[:] = b"\x00" * len(token)

        final = gate.snapshot()
        self.assertEqual(final.state, "VERIFIED")
        self.assertEqual((final.event_calls, final.preflight_calls, final.roundtrip_calls), (1, 1, 1))
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(token))

    async def test_generic_or_out_of_order_confirmation_is_terminal(self):
        async def preflight(*_args):
            raise AssertionError("must stay inert")

        async def roundtrip(*_args):
            raise AssertionError("must stay inert")

        for action in ("generic", "second_first"):
            gate = EventScopedR1Gate(
                preflight=preflight, roundtrip=roundtrip, execution_enabled=True
            )
            if action == "generic":
                snapshot = gate.accept_first_confirmation_once("sp")
            else:
                snapshot = gate.accept_second_confirmation_once(
                    EVENT_R1_SECOND_CONFIRMATION
                )
            self.assertEqual(snapshot.state, "NO-GO")

    async def test_default_is_dormant_and_event_does_nothing(self):
        calls = 0

        async def operation(*_args):
            nonlocal calls
            calls += 1

        gate = EventScopedR1Gate(preflight=operation, roundtrip=operation)
        token = bytearray(b"fixture")
        view = StoredOAuthAccessView(token)
        await gate.observe(event(), receipt(), settings(), view)
        self.assertEqual(gate.snapshot().state, "DORMANT")
        self.assertEqual(calls, 0)
        view.close()
        token[:] = b"\x00" * len(token)


if __name__ == "__main__":
    unittest.main()
