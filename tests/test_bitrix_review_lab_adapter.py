import unittest
from pathlib import Path

import httpx

from bitrix_connector.models import ConnectorEventStatus
from bitrix_connector.review_lab_adapter import (
    AUDIT_EVENTS_PATH,
    FixtureReviewLabAdapter,
    HttpReviewLabAdapter,
    ReviewLabAdapterError,
    ReviewLabController,
    ReviewLabSource,
    build_fixture_audit_detail,
)


class FixtureReviewLabAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_loads_dynamic_read_only_fixture_snapshot(self):
        snapshot = await ReviewLabController(
            FixtureReviewLabAdapter()
        ).load()

        self.assertEqual(snapshot.source, ReviewLabSource.FIXTURE)
        self.assertTrue(snapshot.read_only)
        self.assertFalse(snapshot.actions_enabled)
        self.assertEqual(snapshot.events.returned, 1)
        self.assertIsNotNone(snapshot.selected)
        self.assertEqual(snapshot.selected.status, ConnectorEventStatus.SHADOWED)
        self.assertFalse(snapshot.selected.workflow_guard.bitrix_send_allowed)
        self.assertIsNone(snapshot.selected.outbound_message_id)
        self.assertIn("SIN CONEXIONES EXTERNAS", snapshot.banner)

    async def test_fixture_filter_and_missing_selection_are_deterministic(self):
        adapter = FixtureReviewLabAdapter()
        empty = await adapter.list_events(status=ConnectorEventStatus.SENT)
        missing = await adapter.get_event("0" * 64)

        self.assertEqual(empty.returned, 0)
        self.assertIsNone(missing)


class HttpReviewLabAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_only_two_authenticated_get_contracts(self):
        detail = build_fixture_audit_detail()
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == AUDIT_EVENTS_PATH:
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "event_key": detail.event_key,
                                "status": "shadowed",
                                "received_at": detail.received_at.isoformat(),
                                "updated_at": detail.updated_at.isoformat(),
                                "message_id": 9001,
                                "dialog_id": "chat-controlado-001",
                                "observed_mode": "shadow",
                                "has_nia_response": True,
                                "has_bitrix_preview": True,
                                "bitrix_written": False,
                            }
                        ],
                        "returned": 1,
                    },
                )
            return httpx.Response(
                200,
                json=detail.model_dump(mode="json"),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = HttpReviewLabAdapter(
            base_url="http://review-lab.invalid",
            review_token="private-review-token",
            http_client=client,
        )
        snapshot = await ReviewLabController(adapter).load(
            status=ConnectorEventStatus.SHADOWED,
            limit=1,
        )
        await adapter.close()
        await client.aclose()

        self.assertEqual(snapshot.source, ReviewLabSource.API)
        self.assertEqual(snapshot.events.returned, 1)
        self.assertEqual(snapshot.selected.event_key, detail.event_key)
        self.assertEqual([request.method for request in requests], ["GET", "GET"])
        self.assertEqual(requests[0].url.path, AUDIT_EVENTS_PATH)
        self.assertEqual(
            requests[1].url.path,
            f"{AUDIT_EVENTS_PATH}/{detail.event_key}",
        )
        self.assertEqual(requests[0].url.params["status"], "shadowed")
        self.assertEqual(requests[0].url.params["limit"], "1")
        self.assertEqual(
            requests[0].headers["authorization"],
            "Bearer private-review-token",
        )
        self.assertNotIn("private-review-token", repr(adapter))
        self.assertFalse(snapshot.actions_enabled)

    async def test_errors_are_stable_and_never_include_remote_body(self):
        secret_body = "remote-private-detail"

        def handler(_request):
            return httpx.Response(503, text=secret_body)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = HttpReviewLabAdapter(
            base_url="http://review-lab.invalid",
            review_token="private-review-token",
            http_client=client,
        )

        with self.assertRaises(ReviewLabAdapterError) as captured:
            await adapter.list_events()

        self.assertEqual(captured.exception.code, "review_lab_api_unavailable")
        self.assertNotIn(secret_body, str(captured.exception))
        self.assertNotIn("private-review-token", str(captured.exception))
        await client.aclose()

    async def test_missing_detail_returns_none_without_alternative_call(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(404, json={"detail": "audit_event_not_found"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = HttpReviewLabAdapter(
            base_url="http://review-lab.invalid",
            review_token="private-review-token",
            http_client=client,
        )

        result = await adapter.get_event("0" * 64)

        self.assertIsNone(result)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "GET")
        await client.aclose()


class DynamicReviewLabDemoTests(unittest.TestCase):
    def test_demo_uses_local_adapter_and_exposes_no_write_action(self):
        html = (
            Path(__file__).parents[1]
            / "bitrix_connector"
            / "review_lab_dynamic_demo.html"
        ).read_text(encoding="utf-8")

        self.assertIn('data-source="fixture"', html)
        self.assertIn('data-read-only="true"', html)
        self.assertIn("async listEvents()", html)
        self.assertIn("async getEvent(eventKey)", html)
        self.assertIn("actions_enabled:false", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertEqual(html.count("<button disabled>"), 4)
        self.assertIn("Rechazar salida", html)
        self.assertNotIn("<button disabled>Enviar a Bitrix</button>", html)
        self.assertIn("el runtime real permanece off", html)
        self.assertIn('id="refreshButton"', html)
        self.assertIn('"[REDACTED]"', html)
        self.assertIn("Procedencia de esta evidencia", html)
        self.assertIn("NINGUNA · NO ES UNA NEGOCIACIÓN REAL", html)
        self.assertIn("CAPTURA DE PRUEBA · MAIN.PY + RESPONSE_ENGINE REALES", html)
        self.assertIn("SESIÓN Y CATÁLOGO EN MEMORIA · OPENAI NO USADO", html)
        self.assertIn("LAB-001", html)
        self.assertIn("LAB-002", html)
        self.assertIn('id="composedWorkerFixture"', html)
        self.assertIn("WORKER COMPUESTO HERMÉTICO", html)
        self.assertIn("needs_output_review", html)
        self.assertIn("effective_mode real = off", html)
        self.assertIn("política del ensayo = review", html)
        self.assertIn("Compuertas piloto antes de cada cliente", html)
        self.assertIn('id="pilotIdentity"', html)
        self.assertIn('id="pilotGates"', html)
        self.assertIn('"pilot_enabled":false', html)
        self.assertIn('"pilot_emergency_stop":true', html)
        self.assertIn('"target":"NIA"', html)
        self.assertIn('"target":"Bitrix"', html)
        self.assertIn("pilot_scope_allowed", html)
        self.assertIn("outside_pilot_scope", html)
        self.assertIn("pilot_scope_expired", html)
        self.assertIn("pilot_emergency_stop", html)
        self.assertIn("compuerta no alcanzada · 0 intentos Bitrix", html)
        self.assertIn("controlled-human-reviewer", html)
        self.assertIn('"nia_http_requests":1', html)
        self.assertIn('"bitrix_attempt_count":0', html)
        self.assertIn('"openai_attempt_count":0', html)
        self.assertIn("Cliente · turno 2 · misma sesión", html)
        self.assertIn("fixtureDetails.length", html)
        self.assertIn("contacto-controlado (ficticio)", html)


if __name__ == "__main__":
    unittest.main()
