import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx

from bitrix_connector.review_admin import (
    CSRF_HEADER,
    ReviewAdminAuthenticationOutcome,
    ReviewAdminSafetyState,
)
from bitrix_connector.review_admin_bootstrap import (
    OneTimeReviewAdminAuthenticator,
)
from bitrix_connector.review_admin_entrypoint import (
    create_review_admin_entrypoint,
)
from bitrix_connector.review_admin_session import (
    InMemoryReviewAdminSessionStore,
)
from bitrix_connector.review_approval import ReviewDecisionAction
from bitrix_connector.review_lab_decision_adapter import ReviewLabDecisionResult
from bitrix_connector.review_lab_adapter import (
    FixtureReviewLabAdapter,
    ReviewLabController,
)


ORIGIN = "https://review-admin.test"
BOOTSTRAP_CODE = "bootstrap-controlado-00000000000000000001"
NOW = datetime(2026, 7, 23, 21, 0, tzinfo=timezone.utc)
EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")
SESSION_TOKEN = "session-entrypoint-controlado-00000001"
CSRF_TOKEN = "csrf-entrypoint-controlado-00000000001"


class MutableClock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value


class ClosingDecisionController:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def decide(self, **values):
        self.calls.append(values)
        return ReviewLabDecisionResult(
            action=values["action"],
            path=f"/bitrix-connector/review/{values['event_key']}/approve-input",
            request_payload={
                "content_hash": values["content_hash"],
                "decision_id": str(values["decision_id"]),
            },
            status_code=200,
            code="review_applied",
            visual_state="applied",
        )

    async def close(self):
        self.closed = True


def off_state():
    return ReviewAdminSafetyState(
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        pilot_enabled=False,
        pilot_emergency_stop=True,
    )


def review_state():
    return ReviewAdminSafetyState(
        effective_mode="review",
        activation_locked=False,
        external_calls_enabled=True,
        pilot_enabled=True,
        pilot_emergency_stop=False,
    )


def token_factory():
    values = iter((SESSION_TOKEN, CSRF_TOKEN))
    return lambda: next(values)


def same_origin_headers(**extra):
    return {
        "Origin": ORIGIN,
        "Sec-Fetch-Site": "same-origin",
        **extra,
    }


class OneTimeReviewAdminAuthenticatorTests(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock()

    def build(self, **changes):
        values = {
            "bootstrap_code": BOOTSTRAP_CODE,
            "actor": "controlled-reviewer",
            "credential_id": "bootstrap:controlled:v1",
            "clock": self.clock,
        }
        values.update(changes)
        return OneTimeReviewAdminAuthenticator(**values)

    def test_code_is_hashed_and_can_authenticate_only_once(self):
        authenticator = self.build()

        wrong = authenticator.authenticate(
            "bootstrap-incorrecto-000000000000000000"
        )
        accepted = authenticator.authenticate(BOOTSTRAP_CODE)
        replay = authenticator.authenticate(BOOTSTRAP_CODE)

        self.assertEqual(
            wrong.outcome,
            ReviewAdminAuthenticationOutcome.UNAUTHORIZED,
        )
        self.assertEqual(
            accepted.outcome,
            ReviewAdminAuthenticationOutcome.AUTHENTICATED,
        )
        self.assertEqual(accepted.principal.actor, "controlled-reviewer")
        self.assertEqual(accepted.principal.authenticated_at, NOW)
        self.assertEqual(
            replay.outcome,
            ReviewAdminAuthenticationOutcome.UNAVAILABLE,
        )
        self.assertTrue(authenticator.consumed)
        self.assertNotIn(BOOTSTRAP_CODE, repr(authenticator.__dict__))
        self.assertNotIn(
            "bootstrap-incorrecto",
            repr(authenticator.__dict__),
        )

    def test_expiry_attempt_limit_and_close_are_fail_closed(self):
        expired = self.build()
        self.clock.value = NOW + timedelta(minutes=5)
        self.assertEqual(
            expired.authenticate(BOOTSTRAP_CODE).outcome,
            ReviewAdminAuthenticationOutcome.UNAVAILABLE,
        )

        self.clock.value = NOW
        limited = self.build(max_attempts=2)
        for _ in range(2):
            self.assertEqual(
                limited.authenticate("x").outcome,
                ReviewAdminAuthenticationOutcome.UNAUTHORIZED,
            )
        self.assertEqual(limited.attempts_remaining, 0)
        self.assertEqual(
            limited.authenticate(BOOTSTRAP_CODE).outcome,
            ReviewAdminAuthenticationOutcome.UNAVAILABLE,
        )

        closed = self.build()
        closed.close()
        self.assertTrue(closed.closed)
        self.assertEqual(
            closed.authenticate(BOOTSTRAP_CODE).outcome,
            ReviewAdminAuthenticationOutcome.UNAVAILABLE,
        )

    def test_invalid_configuration_never_builds_an_authenticator(self):
        cases = (
            {"bootstrap_code": "corto"},
            {"ttl": timedelta(0)},
            {"max_attempts": 0},
            {"actor": ""},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.build(**changes)


class ReviewAdminEntrypointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.authenticator = OneTimeReviewAdminAuthenticator(
            bootstrap_code=BOOTSTRAP_CODE,
            actor="controlled-reviewer",
            credential_id="bootstrap:controlled:v1",
            clock=self.clock,
        )
        self.controller = ClosingDecisionController()
        self.sessions = InMemoryReviewAdminSessionStore(
            clock=self.clock,
            token_factory=token_factory(),
        )
        self.safety = off_state
        self.review_controller = ReviewLabController(FixtureReviewLabAdapter())
        self.app = create_review_admin_entrypoint(
            admin_origin=ORIGIN,
            authenticator=self.authenticator,
            decision_controller=self.controller,
            review_controller=self.review_controller,
            safety_loader=lambda: self.safety(),
            session_store=self.sessions,
        )

    async def test_exact_host_is_accepted_without_cors_and_others_are_rejected(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            accepted = await client.get("/", headers={"Origin": ORIGIN})
            rejected = await client.get(
                "/",
                headers={"Host": "attacker.test", "Origin": ORIGIN},
            )

        self.assertEqual(accepted.status_code, 200)
        self.assertNotIn("access-control-allow-origin", accepted.headers)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.app.state.review_admin_trusted_host, "review-admin.test")

    async def test_one_time_login_and_double_only_server_composition(self):
        self.safety = review_state
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            login = await client.post(
                "/session",
                headers=same_origin_headers(),
                json={"credential": BOOTSTRAP_CODE},
            )
            replay_login = await client.post(
                "/session",
                headers=same_origin_headers(),
                json={"credential": BOOTSTRAP_CODE},
            )
            decision = await client.post(
                f"/decisions/{EVENT_KEY}/approve-input",
                headers=same_origin_headers(
                    **{CSRF_HEADER: login.json()["csrf_token"]}
                ),
                json={
                    "content_hash": CONTENT_HASH,
                    "decision_id": str(DECISION_ID),
                    "confirmation": "APROBAR ENVIO A NIA",
                },
            )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(replay_login.status_code, 503)
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(len(self.controller.calls), 1)
        call = self.controller.calls[0]
        self.assertEqual(call["action"], ReviewDecisionAction.APPROVE_INPUT)
        self.assertNotIn("credential", call)
        self.assertNotIn("authorization", call)
        self.assertNotIn(BOOTSTRAP_CODE, repr(call))

    async def test_entrypoint_lifespan_closes_sessions_auth_and_controller(self):
        issued = self.sessions.issue(
            self.authenticator.authenticate(BOOTSTRAP_CODE).principal
        )

        async with self.app.router.lifespan_context(self.app):
            self.assertTrue(self.sessions.resolve(issued.session_id).authenticated)
            self.assertFalse(self.controller.closed)

        self.assertTrue(self.sessions.closed)
        self.assertTrue(self.authenticator.closed)
        self.assertTrue(self.controller.closed)


class ReviewAdminEntrypointIsolationTests(unittest.TestCase):
    def test_entrypoint_is_factory_only_and_not_mounted_or_configured(self):
        sources = "".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                "bitrix_connector/review_admin_bootstrap.py",
                "bitrix_connector/review_admin_entrypoint.py",
            )
        )
        for path in ("main.py", "bitrix_connector/router.py"):
            mounted = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("create_review_admin_entrypoint", mounted)
            self.assertNotIn("review_admin_entrypoint", mounted)
        self.assertNotIn("load_settings", sources)
        self.assertNotIn("os.environ", sources)
        self.assertNotIn("CORSMiddleware", sources)
        self.assertNotIn("httpx", sources)
        self.assertNotIn("uvicorn", sources)
        self.assertNotIn("app = create_review_admin_entrypoint", sources)


if __name__ == "__main__":
    unittest.main()
