import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.bitrix_event_scoped_r1_control import (
    EventScopedR1SessionOwner,
    build_event_r1_control_router,
)
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
from bitrix_connector.review_auth import SingleReviewerAuthenticator


TOKEN = "review-token-fixture-1234567890"
AUTHORIZATION = {"Authorization": f"Bearer {TOKEN}"}


def preflight_outcome():
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


def controlled_event():
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
            "member_id": "member-controlled",
        }
    )


def inert_receipt():
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


def controlled_settings():
    return load_settings(
        {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-controlled",
        }
    )


class VerifiedResult:
    state = "VERIFIED"


def gate_factory(calls=None):
    calls = calls if calls is not None else []

    async def preflight(_settings, view):
        calls.append(("preflight", view.read_text()))
        return preflight_outcome()

    async def roundtrip(_settings, view, outcome, event):
        calls.append(
            (
                "roundtrip",
                view.read_text(),
                outcome.require_anchor().baseline_last_message_id,
                event.chat_id,
            )
        )
        return VerifiedResult()

    return EventScopedR1Gate(
        preflight=preflight,
        roundtrip=roundtrip,
        execution_enabled=True,
    )


def authenticator():
    return SingleReviewerAuthenticator(
        review_token=TOKEN,
        actor="reviewer",
        credential_id="credential-fixture",
    )


class EventScopedR1SessionOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_sequence_expires_and_cannot_rearm(self):
        now = [1000.0]
        owner = EventScopedR1SessionOwner(
            gate_factory,
            ttl_seconds=60,
            clock=lambda: now[0],
        )
        first = await owner.accept_first_confirmation_once(
            EVENT_R1_FIRST_CONFIRMATION
        )
        self.assertEqual(first.state, "AWAITING-MANUAL-REMOVAL")
        now[0] += 61
        expired = await owner.snapshot()
        self.assertEqual(expired.state, "EXPIRED")
        rejected = await owner.accept_first_confirmation_once(
            EVENT_R1_FIRST_CONFIRMATION
        )
        self.assertEqual(rejected.state, "NO-GO")
        self.assertEqual(rejected.retry_budget, 0)

    async def test_disarm_is_terminal_and_drops_attention(self):
        owner = EventScopedR1SessionOwner(gate_factory)
        await owner.accept_first_confirmation_once(EVENT_R1_FIRST_CONFIRMATION)
        await owner.confirm_manual_removal_once(confirmed=True)
        armed = await owner.accept_second_confirmation_once(
            EVENT_R1_SECOND_CONFIRMATION
        )
        self.assertTrue(armed.attention_required_now)
        disarmed = await owner.disarm_once()
        self.assertEqual(disarmed.state, "DISARMED")
        self.assertFalse(disarmed.attention_required_now)
        self.assertEqual(disarmed.disarm_calls, 1)
        repeated = await owner.disarm_once()
        self.assertEqual(repeated.state, "NO-GO")

    async def test_observer_consumes_only_one_exact_event(self):
        calls = []
        owner = EventScopedR1SessionOwner(lambda: gate_factory(calls))
        await owner.accept_first_confirmation_once(EVENT_R1_FIRST_CONFIRMATION)
        await owner.confirm_manual_removal_once(confirmed=True)
        await owner.accept_second_confirmation_once(EVENT_R1_SECOND_CONFIRMATION)
        token = bytearray(b"event-token-fixture")
        view = StoredOAuthAccessView(token)
        await owner.observe(
            controlled_event(), inert_receipt(), controlled_settings(), view
        )
        await owner.observe(
            controlled_event(), inert_receipt(), controlled_settings(), view
        )
        final = await owner.snapshot()
        view.close()
        token[:] = b"\x00" * len(token)

        self.assertEqual(final.state, "VERIFIED")
        self.assertEqual(
            (final.event_calls, final.preflight_calls, final.roundtrip_calls),
            (1, 1, 1),
        )
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(token))


class EventScopedR1ControlRouterTests(unittest.TestCase):
    def app_and_owner(self):
        owner = EventScopedR1SessionOwner(gate_factory)
        app = FastAPI()
        app.include_router(build_event_r1_control_router(owner, authenticator()))
        return app, owner

    def test_requires_auth_and_never_echoes_confirmation(self):
        app, _owner = self.app_and_owner()
        with TestClient(app) as client:
            unauthorized = client.get("/internal/r1-event/status")
            first = client.post(
                "/internal/r1-event/first-confirmation",
                headers=AUTHORIZATION,
                json={"confirmation": EVENT_R1_FIRST_CONFIRMATION},
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["state"], "AWAITING-MANUAL-REMOVAL")
        self.assertNotIn(EVENT_R1_FIRST_CONFIRMATION, first.text)
        self.assertEqual(first.headers["cache-control"], "no-store")

    def test_full_http_sequence_reaches_attention_and_generic_retry_is_no_go(self):
        app, _owner = self.app_and_owner()
        with TestClient(app) as client:
            first = client.post(
                "/internal/r1-event/first-confirmation",
                headers=AUTHORIZATION,
                json={"confirmation": EVENT_R1_FIRST_CONFIRMATION},
            )
            manual = client.post(
                "/internal/r1-event/manual-removal",
                headers=AUTHORIZATION,
                json={"confirmed": True},
            )
            second = client.post(
                "/internal/r1-event/second-confirmation",
                headers=AUTHORIZATION,
                json={"confirmation": EVENT_R1_SECOND_CONFIRMATION},
            )
            retry = client.post(
                "/internal/r1-event/second-confirmation",
                headers=AUTHORIZATION,
                json={"confirmation": "sp"},
            )
        self.assertEqual(
            (first.status_code, manual.status_code, second.status_code),
            (200, 200, 200),
        )
        self.assertTrue(second.json()["attention_required_now"])
        self.assertTrue(second.json()["connector_locked_off"])
        self.assertFalse(second.json()["persisted"])
        self.assertEqual(retry.status_code, 409)
        self.assertEqual(retry.json()["state"], "NO-GO")

    def test_payloads_are_strict_and_invalid_shape_does_not_start_session(self):
        app, _owner = self.app_and_owner()
        with TestClient(app) as client:
            invalid = client.post(
                "/internal/r1-event/first-confirmation",
                headers=AUTHORIZATION,
                json={"confirmation": EVENT_R1_FIRST_CONFIRMATION, "extra": True},
            )
            status = client.get(
                "/internal/r1-event/status", headers=AUTHORIZATION
            )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(status.json()["state"], "IDLE")
        self.assertFalse(status.json()["consumed"])


if __name__ == "__main__":
    unittest.main()
