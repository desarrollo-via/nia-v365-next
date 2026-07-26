import ast
import inspect
import unittest
from copy import deepcopy
from pathlib import Path

from bitrix_connector.audit_service import (
    AuditDocumentInvalid,
    ConnectorAuditService,
)
from bitrix_connector.models import ConnectorEventStatus
from bitrix_connector.review_lab import build_simulated_review_lab_view


def shadow_document():
    view = build_simulated_review_lab_view()
    return {
        "event_key": view.event_key,
        "status": ConnectorEventStatus.SHADOWED.value,
        "received_at": view.received_at,
        "updated_at": view.updated_at,
        "raw_redacted": {
            **view.original_event_redacted,
            "data[bot][auth][access_token]": "must-redact-again",
        },
        "identity_verified": True,
        "security_reason": "identity_verified",
        "attempt_count": 1,
        "nia_attempt_count": 1,
        "bitrix_attempt_count": 0,
        "processing_stage": None,
        "last_error": None,
        "preflight_review": {
            "schema_version": 1,
            "event_key": view.event_key,
            "content_hash": view.input_content_hash,
            "decision": "ready_for_review",
            "raw_redacted": view.original_event_redacted,
            "normalized_input": view.normalized_message.model_dump(mode="python"),
            "preflight_manifest": view.attachment_manifest.model_dump(mode="python"),
            "nia_payload_preview": view.nia_payload.model_dump(mode="python"),
        },
        "input_decision": {
            "decision": "approved",
            "source": "mode_policy",
            "effective_mode": "shadow",
            "content_hash": view.input_content_hash,
            "actor": "mode-policy",
            "reason": "workflow_auto_input",
            "decided_at": view.updated_at,
        },
        "nia_response": view.nia_response.model_dump(mode="python"),
        "output_review": {
            "schema_version": 1,
            "event_key": view.event_key,
            "content_hash": view.output_content_hash,
            "decision": "ready_for_review",
            "blocking_reasons": [],
            "nia_response": view.nia_response.model_dump(mode="python"),
            "bitrix_payload_preview": view.bitrix_payload_preview.model_dump(
                mode="python"
            ),
        },
        "output_decision": None,
        "workflow_guard": view.workflow_guard.model_dump(mode="python"),
        "shadow_result": {
            "reason": "bitrix_suppressed_by_shadow",
            "effective_mode": "shadow",
            "content_hash": view.output_content_hash,
            "completed_at": view.updated_at,
        },
        "outbound_message_id": None,
        "private_internal_field": "must-not-leak",
    }


class FakeAuditStore:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    async def list_audit_events(self, *, status=None, limit=50):
        self.calls.append(("list", status, limit))
        rows = self.documents
        if status is not None:
            rows = [row for row in rows if row["status"] == status]
        return deepcopy(rows[:limit])

    async def get_audit_event(self, event_key):
        self.calls.append(("get", event_key))
        return deepcopy(
            next(
                (row for row in self.documents if row["event_key"] == event_key),
                None,
            )
        )


class ConnectorAuditServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.document = shadow_document()
        self.store = FakeAuditStore([self.document])
        self.service = ConnectorAuditService(self.store)

    async def test_list_is_summary_only_and_forwards_exact_filter(self):
        response = await self.service.list_events(
            status=ConnectorEventStatus.SHADOWED,
            limit=1,
        )
        serialized = response.model_dump_json()

        self.assertEqual(response.returned, 1)
        self.assertEqual(response.items[0].status, ConnectorEventStatus.SHADOWED)
        self.assertEqual(response.items[0].dialog_id, "chat-controlado-001")
        self.assertTrue(response.items[0].has_nia_response)
        self.assertTrue(response.items[0].has_bitrix_preview)
        self.assertFalse(response.items[0].bitrix_written)
        self.assertEqual(self.store.calls, [("list", "shadowed", 1)])
        self.assertNotIn("Necesito una bomba", serialized)
        self.assertNotIn("respuesta", serialized)
        self.assertNotIn("private_internal_field", serialized)

    async def test_detail_exposes_six_artifacts_and_redacts_again(self):
        response = await self.service.get_event(self.document["event_key"])
        serialized = response.model_dump_json()

        self.assertIsNotNone(response.normalized_message)
        self.assertIsNotNone(response.attachment_manifest)
        self.assertIsNotNone(response.nia_payload)
        self.assertIsNotNone(response.nia_response)
        self.assertIsNotNone(response.bitrix_payload_preview)
        self.assertIsNotNone(response.shadow_result)
        self.assertEqual(
            response.original_event_redacted[
                "data[bot][auth][access_token]"
            ],
            "[REDACTED]",
        )
        self.assertFalse(response.workflow_guard.bitrix_send_allowed)
        self.assertIsNone(response.outbound_message_id)
        self.assertEqual(response.attempts.bitrix, 0)
        self.assertNotIn("must-redact-again", serialized)
        self.assertNotIn("private_internal_field", serialized)
        self.assertEqual(self.store.calls, [("get", self.document["event_key"])])

    async def test_missing_event_returns_none_without_fallback_queries(self):
        missing = await self.service.get_event("0" * 64)

        self.assertIsNone(missing)
        self.assertEqual(self.store.calls, [("get", "0" * 64)])

    async def test_invalid_persisted_decision_fails_with_safe_error(self):
        self.document["input_decision"]["unexpected"] = "private"

        with self.assertRaisesRegex(
            AuditDocumentInvalid,
            "audit_document_invalid",
        ):
            await self.service.get_event(self.document["event_key"])

    def test_service_public_async_surface_is_read_only(self):
        public_async = {
            name
            for name, member in inspect.getmembers(
                ConnectorAuditService,
                inspect.iscoroutinefunction,
            )
            if not name.startswith("_")
        }

        self.assertEqual(public_async, {"list_events", "get_event"})

    def test_router_source_declares_only_get_operations_and_no_store(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "bitrix_connector"
            / "audit_router.py"
        )
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        route_methods = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                call = decorator if isinstance(decorator, ast.Call) else None
                attribute = call.func if call is not None else None
                if isinstance(attribute, ast.Attribute):
                    route_methods.append(attribute.attr)

        self.assertEqual(route_methods, ["get", "get"])
        self.assertIn('response.headers["Cache-Control"] = "no-store"', source)
        self.assertIn("validate_review_access", source)
        self.assertIn("factory.open(settings)", source)
        self.assertLess(
            source.index("validate_review_access"),
            source.index("factory.open(settings)"),
        )
        self.assertNotIn("ConnectorRuntime", source)
        self.assertNotIn("@router.post", source)
        self.assertNotIn("@router.patch", source)
        self.assertNotIn("@router.delete", source)


if __name__ == "__main__":
    unittest.main()
