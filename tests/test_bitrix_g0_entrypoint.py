import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from bitrix_connector.config import load_settings
from bitrix_connector.g0_entrypoint import (
    G0_HEALTH_PATH,
    G0_WEBHOOK_PATH,
    create_g0_entrypoint,
)
from bitrix_connector.g0_guard import G0IngressLimits, G0StopController


ORIGIN = "https://bot.example.com"


def off_settings():
    return load_settings(
        {
            "NIA_BITRIX_MODE": "active",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-123",
            "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        }
    )


def official_form():
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "456",
        "data[message][id]": "9001",
        "data[message][chatId]": "78733",
        "data[message][authorId]": "27",
        "data[message][text]": "mensaje controlado",
        "data[chat][dialogId]": "chat78733",
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": "member-123",
        "auth[application_token]": "application-secret",
        "auth[access_token]": "oauth-secret",
    }


class G0EntrypointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = create_g0_entrypoint(
            public_origin=ORIGIN,
            settings_loader=off_settings,
        )

    async def test_exposes_only_health_and_webhook(self):
        routes = {
            (route.path, frozenset(route.methods or ()))
            for route in self.app.routes
        }
        self.assertEqual(
            routes,
            {
                (G0_HEALTH_PATH, frozenset({"GET"})),
                (G0_WEBHOOK_PATH, frozenset({"POST"})),
            },
        )

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            health = await client.get(G0_HEALTH_PATH)
            absent = await client.post("/bitrix-connector/installation")
            docs = await client.get("/docs")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(
            health.json(),
            {
                "status": "ok",
                "service": "bitrix_g0_ingress",
                "version": "v0.097",
                "effective_mode": "off",
                "activation_locked": True,
                "external_calls_enabled": False,
                "pilot_enabled": False,
                "pilot_emergency_stop": True,
                "accepting_webhooks": True,
            },
        )
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(docs.status_code, 404)

    async def test_exact_host_is_required(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            accepted = await client.get(G0_HEALTH_PATH)
            rejected = await client.post(
                G0_WEBHOOK_PATH,
                headers={"Host": "attacker.example.com"},
                data=official_form(),
            )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.app.state.bitrix_g0_guard.tracked_request_count, 0)
        self.assertEqual(
            self.app.state.bitrix_g0_trusted_host,
            "bot.example.com",
        )

    async def test_off_webhook_is_authenticated_redacted_and_inert(self):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            response = await client.post(G0_WEBHOOK_PATH, data=official_form())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "disabled")
        self.assertEqual(payload["reason"], "connector_locked_off")
        self.assertEqual(payload["effective_mode"], "off")
        self.assertTrue(payload["identity_verified"])
        self.assertFalse(payload["persisted"])
        self.assertFalse(payload["nia_called"])
        self.assertFalse(payload["bitrix_written"])
        self.assertFalse(self.app.state.bitrix_g0_runtime_attached)
        self.assertNotIn("application-secret", response.text)
        self.assertNotIn("oauth-secret", response.text)

    async def test_rejects_declared_and_streamed_oversized_bodies(self):
        app = create_g0_entrypoint(
            public_origin=ORIGIN,
            settings_loader=off_settings,
            limits=G0IngressLimits(max_body_bytes=32),
        )
        transport = httpx.ASGITransport(app=app)

        async def chunks():
            yield b"x" * 20
            yield b"y" * 20

        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            declared = await client.post(G0_WEBHOOK_PATH, content=b"x" * 33)
            streamed = await client.post(G0_WEBHOOK_PATH, content=chunks())

        for response in (declared, streamed):
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()["reason"], "g0_body_too_large")
            self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(app.state.bitrix_g0_guard.tracked_request_count, 1)

    async def test_rate_window_is_global_bounded_and_retryable(self):
        now = [100.0]
        app = create_g0_entrypoint(
            public_origin=ORIGIN,
            settings_loader=off_settings,
            limits=G0IngressLimits(
                rate_limit_requests=2,
                rate_window_seconds=10,
            ),
            clock=lambda: now[0],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            first = await client.post(G0_WEBHOOK_PATH, data=official_form())
            second = await client.post(G0_WEBHOOK_PATH, data=official_form())
            limited = await client.post(G0_WEBHOOK_PATH, data=official_form())
            now[0] += 11
            renewed = await client.post(G0_WEBHOOK_PATH, data=official_form())

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["reason"], "g0_rate_limited")
        self.assertEqual(limited.headers["retry-after"], "10")
        self.assertEqual(renewed.status_code, 200)
        self.assertEqual(app.state.bitrix_g0_guard.tracked_request_count, 1)

    async def test_timeout_cancels_handler_and_returns_safe_response(self):
        cancelled = asyncio.Event()

        async def slow_handler(*args, **kwargs):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        app = create_g0_entrypoint(
            public_origin=ORIGIN,
            settings_loader=off_settings,
            limits=G0IngressLimits(request_timeout_seconds=0.01),
        )
        transport = httpx.ASGITransport(app=app)
        with patch(
            "bitrix_connector.g0_entrypoint.handle_bitrix_webhook",
            new=slow_handler,
        ):
            async with httpx.AsyncClient(
                transport=transport,
                base_url=ORIGIN,
            ) as client:
                response = await client.post(
                    G0_WEBHOOK_PATH,
                    data=official_form(),
                )

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["reason"], "g0_request_timeout")
        self.assertTrue(cancelled.is_set())

    async def test_terminal_stop_rejects_new_and_cancels_inflight_request(self):
        stop = G0StopController()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_handler(*args, **kwargs):
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        app = create_g0_entrypoint(
            public_origin=ORIGIN,
            settings_loader=off_settings,
            stop_controller=stop,
        )
        transport = httpx.ASGITransport(app=app)
        with patch(
            "bitrix_connector.g0_entrypoint.handle_bitrix_webhook",
            new=slow_handler,
        ):
            async with httpx.AsyncClient(
                transport=transport,
                base_url=ORIGIN,
            ) as client:
                pending = asyncio.create_task(
                    client.post(G0_WEBHOOK_PATH, data=official_form())
                )
                await asyncio.wait_for(started.wait(), timeout=1)
                stop.request_stop()
                interrupted = await asyncio.wait_for(pending, timeout=1)
                rejected = await client.post(
                    G0_WEBHOOK_PATH,
                    data=official_form(),
                )
                health = await client.get(G0_HEALTH_PATH)

        self.assertEqual(interrupted.status_code, 503)
        self.assertEqual(interrupted.json()["reason"], "g0_ingress_stopped")
        self.assertTrue(cancelled.is_set())
        self.assertEqual(rejected.status_code, 503)
        self.assertEqual(rejected.json()["reason"], "g0_ingress_stopped")
        self.assertEqual(health.status_code, 200)
        self.assertFalse(health.json()["accepting_webhooks"])


class G0EntrypointConfigurationTests(unittest.TestCase):
    def test_rejects_non_positive_limits(self):
        for values in (
            {"max_body_bytes": 0},
            {"request_timeout_seconds": 0},
            {"rate_limit_requests": 0},
            {"rate_window_seconds": 0},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                G0IngressLimits(**values)

    def test_rejects_non_stable_or_non_https_origins(self):
        for origin in (
            "http://bot.example.com",
            "https://localhost",
            "https://127.0.0.1",
            "https://demo.trycloudflare.com",
            "https://*.example.com",
            "https://bot.example.com/path",
            "https://bot.example.com:8443",
            "https://user:secret@bot.example.com",
            "",
        ):
            with self.subTest(origin=origin), self.assertRaisesRegex(
                ValueError,
                "g0_public_origin_invalid",
            ):
                create_g0_entrypoint(public_origin=origin)

    def test_factory_is_not_mounted_or_globally_configured(self):
        source = Path("bitrix_connector/g0_entrypoint.py").read_text(
            encoding="utf-8"
        )
        for path in ("main.py", "bitrix_connector/router.py"):
            mounted = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("create_g0_entrypoint", mounted)
            self.assertNotIn("g0_entrypoint", mounted)
        self.assertNotIn("CORSMiddleware", source)
        self.assertNotIn("uvicorn", source)
        self.assertNotIn("app = create_g0_entrypoint", source)


if __name__ == "__main__":
    unittest.main()
