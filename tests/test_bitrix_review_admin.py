import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx
from PIL import Image

from bitrix_connector.review_admin import (
    CSRF_HEADER,
    ReviewAdminAuthenticationOutcome,
    ReviewAdminAuthenticationResult,
    ReviewAdminSafetyState,
    create_review_admin_app,
)
from bitrix_connector.review_admin_session import (
    InMemoryReviewAdminSessionStore,
    ReviewAdminSessionOutcome,
    SESSION_COOKIE_NAME,
)
from bitrix_connector.review_approval import ReviewDecisionAction, ReviewPrincipal
from bitrix_connector.review_lab_decision_adapter import ReviewLabDecisionResult
from bitrix_connector.review_lab_adapter import (
    FixtureReviewLabAdapter,
    ReviewLabController,
    build_fixture_audit_detail,
)


ORIGIN = "https://review-admin.test"
NOW = datetime(2026, 7, 23, 20, 0, tzinfo=timezone.utc)
EVENT_KEY = "a" * 64
CONTENT_HASH = "b" * 64
DECISION_ID = UUID("12345678-1234-4678-9234-567812345678")
SESSION_TOKEN = "session-token-controlado-000000000001"
CSRF_TOKEN = "csrf-token-controlado-00000000000001"


class MutableClock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value


class FakeAuthenticator:
    def __init__(self, expected="credencial-controlada"):
        self.expected = expected
        self.calls = []

    def authenticate(self, credential):
        self.calls.append(credential)
        if self.expected is None:
            return ReviewAdminAuthenticationResult(
                outcome=ReviewAdminAuthenticationOutcome.UNAVAILABLE
            )
        if credential != self.expected:
            return ReviewAdminAuthenticationResult(
                outcome=ReviewAdminAuthenticationOutcome.UNAUTHORIZED
            )
        return ReviewAdminAuthenticationResult(
            outcome=ReviewAdminAuthenticationOutcome.AUTHENTICATED,
            principal=ReviewPrincipal(
                actor="controlled-reviewer",
                credential_id="reviewer:controlled:v1",
                authenticated_at=NOW,
            ),
        )


class FakeDecisionController:
    def __init__(self):
        self.calls = []

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
            request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )


def token_factory():
    values = iter(
        (
            SESSION_TOKEN,
            CSRF_TOKEN,
            "session-token-controlado-000000000002",
            "csrf-token-controlado-00000000000002",
        )
    )
    return lambda: next(values)


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


def same_origin_headers(**extra):
    return {
        "Origin": ORIGIN,
        "Sec-Fetch-Site": "same-origin",
        **extra,
    }


class ReviewAdminSessionStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.store = InMemoryReviewAdminSessionStore(
            clock=self.clock,
            token_factory=token_factory(),
        )
        self.principal = ReviewPrincipal(
            actor="controlled-reviewer",
            credential_id="reviewer:controlled:v1",
            authenticated_at=NOW,
        )

    def test_store_keeps_hashes_and_enforces_csrf(self):
        issued = self.store.issue(self.principal)

        self.assertEqual(issued.session_id, SESSION_TOKEN)
        self.assertEqual(issued.csrf_token, CSRF_TOKEN)
        self.assertNotIn(SESSION_TOKEN, repr(self.store._sessions))
        self.assertNotIn(CSRF_TOKEN, repr(self.store._sessions))
        self.assertFalse(
            self.store.resolve(
                SESSION_TOKEN,
                csrf_token="csrf-incorrecto-controlado-000000000",
                require_csrf=True,
            ).authenticated
        )
        self.assertTrue(
            self.store.resolve(
                SESSION_TOKEN,
                csrf_token=CSRF_TOKEN,
                require_csrf=True,
            ).authenticated
        )

    def test_new_login_revokes_the_previous_operator_session(self):
        first = self.store.issue(self.principal)
        second = self.store.issue(self.principal)

        self.assertEqual(
            self.store.resolve(first.session_id).outcome,
            ReviewAdminSessionOutcome.REVOKED,
        )
        self.assertTrue(self.store.resolve(second.session_id).authenticated)
        self.assertEqual(self.store.active_count, 1)

    async def test_idle_absolute_revoke_and_close_fail_closed(self):
        self.store.issue(self.principal)
        self.clock.value = NOW + timedelta(minutes=10)

        idle = self.store.resolve(SESSION_TOKEN)

        self.assertEqual(idle.outcome, ReviewAdminSessionOutcome.EXPIRED)
        self.assertFalse(self.store.resolve(SESSION_TOKEN).authenticated)

        second = self.store.issue(self.principal)
        for minutes in (19, 28, 37):
            self.clock.value = NOW + timedelta(minutes=minutes)
            self.assertTrue(self.store.resolve(second.session_id).authenticated)
        self.clock.value = NOW + timedelta(minutes=39)
        self.assertTrue(self.store.resolve(second.session_id).authenticated)
        self.clock.value = NOW + timedelta(minutes=40)
        self.assertEqual(
            self.store.resolve(second.session_id).outcome,
            ReviewAdminSessionOutcome.EXPIRED,
        )

        await self.store.close()
        self.assertTrue(self.store.closed)
        self.assertEqual(self.store.active_count, 0)
        self.assertEqual(
            self.store.resolve(second.session_id).outcome,
            ReviewAdminSessionOutcome.UNAVAILABLE,
        )
        with self.assertRaisesRegex(
            RuntimeError, "review_admin_session_store_closed"
        ):
            self.store.issue(self.principal)


class ReviewAdminHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.sessions = InMemoryReviewAdminSessionStore(
            clock=self.clock,
            token_factory=token_factory(),
        )
        self.authenticator = FakeAuthenticator()
        self.controller = FakeDecisionController()
        self.review_controller = ReviewLabController(FixtureReviewLabAdapter())
        self.safety = off_state
        self.app = create_review_admin_app(
            admin_origin=ORIGIN,
            authenticator=self.authenticator,
            decision_controller=self.controller,
            review_controller=self.review_controller,
            safety_loader=lambda: self.safety(),
            session_store=self.sessions,
        )

    async def request(self, method, path, **options):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            return await client.request(method, path, **options)

    async def login(self, client):
        return await client.post(
            "/session",
            headers=same_origin_headers(),
            json={"credential": "credencial-controlada"},
        )

    async def test_shell_assets_and_state_are_same_origin_and_hardened(self):
        shell = await self.request("GET", "/")
        script = await self.request("GET", "/assets/review-admin.js")
        state = await self.request("GET", "/state")

        self.assertEqual(shell.status_code, 200)
        self.assertIn('src="./assets/review-admin.js"', shell.text)
        self.assertIn('id="login-form"', shell.text)
        self.assertIn('autocomplete="one-time-code"', shell.text)
        self.assertIn('id="review-panel"', shell.text)
        self.assertNotIn("<script>", shell.text)
        self.assertNotIn("Bearer", shell.text + script.text)
        self.assertNotIn("localStorage", script.text)
        self.assertNotIn("sessionStorage", script.text)
        self.assertIn("window.location.hash", script.text)
        self.assertIn("window.history.replaceState", script.text)
        self.assertIn("parameters.get('nia-bootstrap')", script.text)
        self.assertIn("consumeBootstrapFragment", script.text)
        self.assertNotIn("input.value=fragmentBootstrap", script.text)
        self.assertLess(
            script.text.index("window.location.hash"),
            script.text.index("window.history.replaceState"),
        )
        self.assertLess(
            script.text.index("window.history.replaceState"),
            script.text.index("parameters.get('nia-bootstrap')"),
        )
        self.assertIn("default-src 'self'", shell.headers["content-security-policy"])
        self.assertEqual(shell.headers["x-frame-options"], "DENY")
        self.assertEqual(shell.headers["cache-control"], "no-store")
        self.assertEqual(
            state.json(),
            {
                "effective_mode": "off",
                "activation_locked": True,
                "external_calls_enabled": False,
                "pilot_enabled": False,
                "pilot_emergency_stop": True,
                "decisions_allowed": False,
            },
        )

    async def test_reviews_require_session_and_use_only_injected_get_controller(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            unauthorized = await client.get("/reviews")
            await self.login(client)
            listed = await client.get("/reviews")
            event_key = listed.json()["events"]["items"][0]["event_key"]
            selected = await client.get(f"/reviews/{event_key}")

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["source"], "fixture")
        self.assertTrue(listed.json()["read_only"])
        self.assertFalse(listed.json()["actions_enabled"])
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["selected"]["event_key"], event_key)
        serialized = selected.text
        self.assertNotIn("credential", serialized)
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("Bearer", serialized)

    async def test_active_session_can_rotate_csrf_without_reusing_bootstrap(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            login = await self.login(client)
            rotated = await client.post(
                "/session/csrf",
                headers=same_origin_headers(),
                json={},
            )
            old_logout = await client.request(
                "DELETE",
                "/session",
                headers=same_origin_headers(
                    **{CSRF_HEADER: login.json()["csrf_token"]}
                ),
                json={},
            )
            new_logout = await client.request(
                "DELETE",
                "/session",
                headers=same_origin_headers(
                    **{CSRF_HEADER: rotated.json()["csrf_token"]}
                ),
                json={},
            )

        self.assertEqual(rotated.status_code, 200)
        self.assertNotEqual(
            rotated.json()["csrf_token"],
            login.json()["csrf_token"],
        )
        self.assertEqual(old_logout.status_code, 403)
        self.assertEqual(new_logout.status_code, 200)

    async def test_login_requires_exact_origin_and_sets_host_cookie(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            absent_origin = await client.post(
                "/session",
                headers={"Sec-Fetch-Site": "same-origin"},
                json={"credential": "credencial-controlada"},
            )
            cross_site = await client.post(
                "/session",
                headers={
                    "Origin": "https://attacker.test",
                    "Sec-Fetch-Site": "cross-site",
                },
                json={"credential": "credencial-controlada"},
            )
            response = await self.login(client)
            active = await client.get("/session")

        self.assertEqual(absent_origin.status_code, 403)
        self.assertEqual(cross_site.status_code, 403)
        self.assertEqual(self.authenticator.calls, ["credencial-controlada"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["csrf_token"], CSRF_TOKEN)
        cookie = response.headers["set-cookie"]
        self.assertIn(f"{SESSION_COOKIE_NAME}=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("Path=/", cookie)
        self.assertEqual(active.status_code, 200)
        self.assertNotIn(SESSION_TOKEN, response.text)

    async def test_csrf_and_real_off_gate_precede_body_and_controller(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            await self.login(client)
            path = f"/decisions/{EVENT_KEY}/approve-input"
            missing_csrf = await client.post(
                path,
                headers=same_origin_headers(),
                json={},
            )
            locked = await client.post(
                path,
                headers=same_origin_headers(
                    **{CSRF_HEADER: CSRF_TOKEN, "Content-Type": "application/json"}
                ),
                content=b'{"malformed":',
            )

        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(
            missing_csrf.json()["code"], "review_admin_csrf_invalid"
        )
        self.assertEqual(locked.status_code, 503)
        self.assertEqual(locked.json()["code"], "review_admin_decisions_locked")
        self.assertEqual(self.controller.calls, [])

    async def test_injected_review_state_forwards_only_safe_contract(self):
        self.safety = review_state
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            await self.login(client)
            response = await client.post(
                f"/decisions/{EVENT_KEY}/approve-input",
                headers=same_origin_headers(**{CSRF_HEADER: CSRF_TOKEN}),
                json={
                    "content_hash": CONTENT_HASH,
                    "decision_id": str(DECISION_ID),
                    "confirmation": "APROBAR ENVIO A NIA",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], "review_applied")
        self.assertEqual(len(self.controller.calls), 1)
        call = self.controller.calls[0]
        self.assertEqual(call["action"], ReviewDecisionAction.APPROVE_INPUT)
        self.assertNotIn("credential", call)
        self.assertNotIn("authorization", call)
        self.assertNotIn("actor", call)

    async def test_logout_revokes_server_session_and_clears_cookie(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            await self.login(client)
            logout = await client.request(
                "DELETE",
                "/session",
                headers=same_origin_headers(**{CSRF_HEADER: CSRF_TOKEN}),
                json={},
            )
            after = await client.get("/session")

        self.assertEqual(logout.status_code, 200)
        self.assertIn("Max-Age=0", logout.headers["set-cookie"])
        self.assertEqual(self.sessions.active_count, 0)
        self.assertEqual(after.status_code, 401)

    async def test_application_shutdown_revokes_and_closes_all_sessions(self):
        issued = self.sessions.issue(
            ReviewPrincipal(
                actor="controlled-reviewer",
                credential_id="reviewer:controlled:v1",
                authenticated_at=NOW,
            )
        )

        async with self.app.router.lifespan_context(self.app):
            self.assertTrue(self.sessions.resolve(issued.session_id).authenticated)

        self.assertTrue(self.sessions.closed)
        self.assertEqual(self.sessions.active_count, 0)
        self.assertEqual(
            self.sessions.resolve(issued.session_id).outcome,
            ReviewAdminSessionOutcome.UNAVAILABLE,
        )


class ReviewAdminIsolationTests(unittest.TestCase):
    def test_factory_is_not_mounted_and_contains_no_runtime_dependencies(self):
        source = Path("bitrix_connector/review_admin.py").read_text(encoding="utf-8")
        session_source = Path(
            "bitrix_connector/review_admin_session.py"
        ).read_text(encoding="utf-8")
        for path in ("main.py", "bitrix_connector/router.py"):
            mounted = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("create_review_admin_app", mounted)
            self.assertNotIn("review_admin", mounted)
        for forbidden in (
            "motor",
            "pymongo",
            "MongoClient",
            "load_settings",
            "NiaClient",
            "BitrixClient",
        ):
            self.assertNotIn(forbidden, source + session_source)

    def test_visual_fixture_matches_get_adapter_and_contains_no_secret_or_network(self):
        html = Path(
            "bitrix_connector/review_admin_off_demo.html"
        ).read_text(encoding="utf-8")
        detail = build_fixture_audit_detail()

        self.assertIn('data-visual-fixture="true"', html)
        self.assertIn('data-real-mode="off"', html)
        self.assertIn(detail.event_key, html)
        self.assertIn(detail.input_content_hash, html)
        self.assertIn(detail.output_content_hash, html)
        self.assertIn("Código bootstrap consumido correctamente", html)
        self.assertIn('aria-label="Código bootstrap"', html)
        self.assertEqual(html.count("<article>"), 6)
        self.assertEqual(html.count("<button disabled>"), 4)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("Bearer", html)
        self.assertNotIn("localStorage", html)
        self.assertNotIn("sessionStorage", html)
        screenshot = Path("logs/review_admin_off_demo.png")
        self.assertGreater(screenshot.stat().st_size, 200_000)
        with Image.open(screenshot) as image:
            self.assertEqual(image.size, (1440, 1900))


if __name__ == "__main__":
    unittest.main()
