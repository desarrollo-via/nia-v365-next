import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_dispatch import (
    BitrixDispatchWorkerHandler,
    BitrixDispatchWorkerStore,
)
from bitrix_connector.config import load_settings
from bitrix_connector.config import ConnectorMode
from bitrix_connector.models import ConnectorEventStatus, ConnectorIngestionStatus
from bitrix_connector.mode_policy import ExternalCallPolicy
from bitrix_connector.nia_client import NiaChatResponse, NiaClientResult
from bitrix_connector.nia_dispatch import (
    NiaDispatchWorkerHandler,
    NiaDispatchWorkerStore,
)
from bitrix_connector.preflight_handler import TextPreflightWorkerHandler
from bitrix_connector.review import ReviewDecisionOutcome
from bitrix_connector.service import ConnectorIngestionService
from bitrix_connector.storage import MongoConnectorEventStore
from bitrix_connector.worker import ConnectorWorker, ConnectorWorkerRunStatus


def enabled_review_policy():
    return ExternalCallPolicy(
        effective_mode=ConnectorMode.REVIEW,
        activation_locked=False,
        external_calls_enabled=True,
    )


def enabled_shadow_policy():
    return ExternalCallPolicy(
        effective_mode=ConnectorMode.SHADOW,
        activation_locked=False,
        external_calls_enabled=True,
    )


def enabled_active_policy():
    return ExternalCallPolicy(
        effective_mode=ConnectorMode.ACTIVE,
        activation_locked=False,
        external_calls_enabled=True,
    )


class InMemoryCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        self.documents.sort(
            key=lambda document: document[field],
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.documents):
            raise StopAsyncIteration
        document = self.documents[self._index]
        self._index += 1
        return deepcopy(document)


class InMemoryCollection:
    def __init__(self):
        self.documents = {}

    @staticmethod
    def _field_value(document, field):
        value = document
        for part in field.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _matches(cls, document, selector):
        for field, expected in selector.items():
            if field == "$or":
                if not any(cls._matches(document, item) for item in expected):
                    return False
                continue

            actual = cls._field_value(document, field)
            if isinstance(expected, dict):
                if "$lte" in expected and not actual <= expected["$lte"]:
                    return False
                if "$gt" in expected and not actual > expected["$gt"]:
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
                if "$nin" in expected and actual in expected["$nin"]:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _apply_update(document, update):
        document.update(deepcopy(update.get("$set", {})))
        for field, increment in update.get("$inc", {}).items():
            document[field] += increment

    @staticmethod
    def _project(document, projection):
        if document is None:
            return None
        included = [
            field
            for field, enabled in projection.items()
            if enabled and field != "_id"
        ]
        if not included:
            return deepcopy(document)
        return {
            field: deepcopy(document[field])
            for field in included
            if field in document
        }

    async def update_one(self, selector, update, *, upsert):
        event_key = selector["event_key"]
        if upsert:
            if event_key in self.documents:
                return SimpleNamespace(upserted_id=None, modified_count=0)
            self.documents[event_key] = deepcopy(update["$setOnInsert"])
            return SimpleNamespace(upserted_id=f"memory-{len(self.documents)}")

        document = self.documents.get(event_key)
        if document is None or not self._matches(document, selector):
            return SimpleNamespace(upserted_id=None, modified_count=0)
        self._apply_update(document, update)
        return SimpleNamespace(upserted_id=None, modified_count=1)

    async def find_one(self, selector, projection):
        document = next(
            (
                item
                for item in self.documents.values()
                if self._matches(item, selector)
            ),
            None,
        )
        return self._project(document, projection)

    def find(self, selector, projection):
        return InMemoryCursor(
            [
                self._project(document, projection)
                for document in self.documents.values()
                if self._matches(document, selector)
            ]
        )

    async def find_one_and_update(
        self,
        selector,
        update,
        *,
        sort=None,
        projection=None,
        return_document,
    ):
        candidates = [
            document
            for document in self.documents.values()
            if self._matches(document, selector)
        ]
        if not candidates:
            return None
        document = (
            min(candidates, key=lambda item: item[sort[0][0]])
            if sort
            else candidates[0]
        )
        self._apply_update(document, update)
        return self._project(document, projection or {"_id": 0})


class FakeNiaClient:
    def __init__(self):
        self.payloads = []

    async def send_approved_text(self, payload):
        self.payloads.append(payload)
        return NiaClientResult.succeeded(
            NiaChatResponse(
                respuesta="¿Qué caudal necesita para la bomba?",
                etapa="preguntas_tecnicas",
            ),
            http_status=200,
        )


class FakeBitrixClient:
    def __init__(self):
        self.payloads = []

    async def send_approved_message(self, payload):
        self.payloads.append(payload)
        return BitrixClientResult.succeeded(
            BitrixSendResponse.model_validate(
                {"result": {"id": 987, "uuidMap": {}}}
            ),
            http_status=200,
        )


def event_form():
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "ts": "1772093963",
        "data[bot][id]": "456",
        "data[message][id]": "789",
        "data[message][chatId]": "5",
        "data[message][authorId]": "27",
        "data[message][text]": "Necesito una bomba",
        "data[chat][dialogId]": "chat5",
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "auth[domain]": "viaindustrial.bitrix24.es",
        "auth[member_id]": "member-123",
        "auth[application_token]": "secret-token",
        "data[bot][auth][access_token]": "oauth-secret",
    }


class ConnectorFullFlowTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def settings_for(mode):
        return replace(
            load_settings(
                {
                    "NIA_BITRIX_DOMAIN": "viaindustrial.bitrix24.es",
                    "NIA_BITRIX_MEMBER_ID": "member-123",
                    "NIA_BITRIX_APPLICATION_TOKEN": "secret-token",
                }
            ),
            effective_mode=mode,
            activation_locked=False,
        )

    @staticmethod
    def workers(store, nia_client, bitrix_client, policy_provider, start):
        preflight_worker = ConnectorWorker(
            store,
            TextPreflightWorkerHandler(
                store,
                lease_owner="preflight-worker",
                policy_provider=policy_provider,
                clock=lambda: start + timedelta(seconds=5),
            ),
            lease_owner="preflight-worker",
            lease_seconds=60,
            clock=lambda: start,
        )
        nia_worker = ConnectorWorker(
            NiaDispatchWorkerStore(store),
            NiaDispatchWorkerHandler(
                store,
                nia_client,
                lease_owner="nia-worker",
                policy_provider=policy_provider,
                clock=lambda: start + timedelta(seconds=20),
            ),
            lease_owner="nia-worker",
            lease_seconds=60,
            clock=lambda: start + timedelta(seconds=15),
        )
        bitrix_worker = ConnectorWorker(
            BitrixDispatchWorkerStore(store),
            BitrixDispatchWorkerHandler(
                store,
                bitrix_client,
                lease_owner="bitrix-worker",
                policy_provider=policy_provider,
                clock=lambda: start + timedelta(seconds=35),
            ),
            lease_owner="bitrix-worker",
            lease_seconds=60,
            clock=lambda: start + timedelta(seconds=30),
        )
        return preflight_worker, nia_worker, bitrix_worker

    async def test_full_flow_pauses_for_both_reviews_and_sends_only_once(self):
        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        collection = InMemoryCollection()
        store = MongoConnectorEventStore(collection)
        service = ConnectorIngestionService(store)
        settings = replace(
            load_settings({
                "NIA_BITRIX_DOMAIN": "viaindustrial.bitrix24.es",
                "NIA_BITRIX_MEMBER_ID": "member-123",
                "NIA_BITRIX_APPLICATION_TOKEN": "secret-token",
            }),
            effective_mode=ConnectorMode.REVIEW,
            activation_locked=False,
        )
        nia_client = FakeNiaClient()
        bitrix_client = FakeBitrixClient()

        preflight_worker = ConnectorWorker(
            store,
            TextPreflightWorkerHandler(
                store,
                lease_owner="preflight-worker",
                clock=lambda: start + timedelta(seconds=5),
            ),
            lease_owner="preflight-worker",
            lease_seconds=60,
            clock=lambda: start,
        )
        nia_worker = ConnectorWorker(
            NiaDispatchWorkerStore(store),
            NiaDispatchWorkerHandler(
                store,
                nia_client,
                lease_owner="nia-worker",
                policy_provider=enabled_review_policy,
                clock=lambda: start + timedelta(seconds=20),
            ),
            lease_owner="nia-worker",
            lease_seconds=60,
            clock=lambda: start + timedelta(seconds=15),
        )
        bitrix_worker = ConnectorWorker(
            BitrixDispatchWorkerStore(store),
            BitrixDispatchWorkerHandler(
                store,
                bitrix_client,
                lease_owner="bitrix-worker",
                policy_provider=enabled_review_policy,
                clock=lambda: start + timedelta(seconds=35),
            ),
            lease_owner="bitrix-worker",
            lease_seconds=60,
            clock=lambda: start + timedelta(seconds=30),
        )

        received = await service.ingest(event_form(), settings)
        duplicate_before_processing = await service.ingest(event_form(), settings)

        self.assertEqual(received.status, ConnectorIngestionStatus.STORED)
        self.assertEqual(
            duplicate_before_processing.status,
            ConnectorIngestionStatus.DUPLICATE,
        )
        self.assertEqual(received.event_key, duplicate_before_processing.event_key)

        preflight = await preflight_worker.run_once()
        input_review = await store.get_review(received.event_key)
        nia_before_input_approval = await nia_worker.run_once()

        self.assertEqual(preflight.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(
            input_review["status"],
            ConnectorEventStatus.NEEDS_INPUT_REVIEW.value,
        )
        self.assertEqual(
            nia_before_input_approval.status,
            ConnectorWorkerRunStatus.IDLE,
        )
        self.assertEqual(nia_client.payloads, [])

        input_decision = await store.approve_input(
            received.event_key,
            content_hash=input_review["preflight_review"]["content_hash"],
            actor="human-reviewer",
            now=start + timedelta(seconds=10),
        )
        nia_dispatch = await nia_worker.run_once()
        output_review = await store.get_output_review(received.event_key)
        bitrix_before_output_approval = await bitrix_worker.run_once()

        self.assertEqual(input_decision.outcome, ReviewDecisionOutcome.APPLIED)
        self.assertEqual(nia_dispatch.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(len(nia_client.payloads), 1)
        self.assertEqual(
            output_review["status"],
            ConnectorEventStatus.NEEDS_OUTPUT_REVIEW.value,
        )
        self.assertEqual(
            bitrix_before_output_approval.status,
            ConnectorWorkerRunStatus.IDLE,
        )
        self.assertEqual(bitrix_client.payloads, [])

        output_decision = await store.approve_output(
            received.event_key,
            content_hash=output_review["output_review"]["content_hash"],
            actor="human-reviewer",
            now=start + timedelta(seconds=25),
        )
        bitrix_dispatch = await bitrix_worker.run_once()
        final_document = await store.get_by_key(received.event_key)

        self.assertEqual(output_decision.outcome, ReviewDecisionOutcome.APPLIED)
        self.assertEqual(
            bitrix_dispatch.status,
            ConnectorWorkerRunStatus.COMPLETED,
        )
        self.assertEqual(final_document["event_key"], received.event_key)
        self.assertEqual(final_document["status"], ConnectorEventStatus.SENT.value)
        self.assertEqual(final_document["outbound_message_id"], 987)
        self.assertEqual(len(nia_client.payloads), 1)
        self.assertEqual(len(bitrix_client.payloads), 1)

        duplicate_after_send = await service.ingest(event_form(), settings)
        reruns = [
            await preflight_worker.run_once(),
            await nia_worker.run_once(),
            await bitrix_worker.run_once(),
        ]

        self.assertEqual(
            duplicate_after_send.status,
            ConnectorIngestionStatus.DUPLICATE,
        )
        self.assertEqual(duplicate_after_send.event_key, received.event_key)
        self.assertTrue(
            all(result.status is ConnectorWorkerRunStatus.IDLE for result in reruns)
        )
        self.assertEqual(len(nia_client.payloads), 1)
        self.assertEqual(len(bitrix_client.payloads), 1)

    async def test_shadow_calls_nia_once_and_finishes_without_bitrix(self):
        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        store = MongoConnectorEventStore(InMemoryCollection())
        service = ConnectorIngestionService(store)
        nia_client = FakeNiaClient()
        bitrix_client = FakeBitrixClient()
        preflight, nia, bitrix = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_shadow_policy,
            start,
        )

        received = await service.ingest(
            event_form(),
            self.settings_for(ConnectorMode.SHADOW),
        )
        preflight_result = await preflight.run_once()
        after_preflight = await store.get_by_key(received.event_key)
        nia_result = await nia.run_once()
        bitrix_result = await bitrix.run_once()
        final = await store.get_by_key(received.event_key)

        self.assertEqual(preflight_result.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(
            after_preflight["status"],
            ConnectorEventStatus.READY_FOR_NIA.value,
        )
        self.assertEqual(
            after_preflight["input_decision"]["source"],
            "mode_policy",
        )
        self.assertEqual(nia_result.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(bitrix_result.status, ConnectorWorkerRunStatus.IDLE)
        self.assertEqual(final["status"], ConnectorEventStatus.SHADOWED.value)
        self.assertEqual(
            final["nia_response"]["respuesta"],
            "¿Qué caudal necesita para la bomba?",
        )
        self.assertEqual(
            final["output_review"]["bitrix_payload_preview"]["dialogId"],
            "chat5",
        )
        self.assertEqual(final["shadow_result"]["reason"], "bitrix_suppressed_by_shadow")
        self.assertIsNone(final["outbound_message_id"])
        self.assertEqual(final["bitrix_attempt_count"], 0)
        self.assertEqual(len(nia_client.payloads), 1)
        self.assertEqual(bitrix_client.payloads, [])

    async def test_active_safe_text_flows_without_human_decisions(self):
        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        store = MongoConnectorEventStore(InMemoryCollection())
        service = ConnectorIngestionService(store)
        nia_client = FakeNiaClient()
        bitrix_client = FakeBitrixClient()
        preflight, nia, bitrix = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_active_policy,
            start,
        )

        received = await service.ingest(
            event_form(),
            self.settings_for(ConnectorMode.ACTIVE),
        )
        await preflight.run_once()
        await nia.run_once()
        before_bitrix = await store.get_by_key(received.event_key)
        sent = await bitrix.run_once()
        final = await store.get_by_key(received.event_key)

        self.assertEqual(
            before_bitrix["status"],
            ConnectorEventStatus.READY_FOR_BITRIX.value,
        )
        self.assertEqual(before_bitrix["output_decision"]["source"], "mode_policy")
        self.assertEqual(sent.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(final["status"], ConnectorEventStatus.SENT.value)
        self.assertEqual(len(nia_client.payloads), 1)
        self.assertEqual(len(bitrix_client.payloads), 1)

    async def test_active_auto_input_downgrades_to_human_review_before_nia(self):
        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        store = MongoConnectorEventStore(InMemoryCollection())
        service = ConnectorIngestionService(store)
        nia_client = FakeNiaClient()
        bitrix_client = FakeBitrixClient()
        preflight, _, _ = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_active_policy,
            start,
        )
        _, review_nia, _ = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_review_policy,
            start,
        )

        received = await service.ingest(
            event_form(),
            self.settings_for(ConnectorMode.ACTIVE),
        )
        await preflight.run_once()
        reconciled = await review_nia.run_once()
        final = await store.get_by_key(received.event_key)

        self.assertEqual(reconciled.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(
            final["status"],
            ConnectorEventStatus.NEEDS_INPUT_REVIEW.value,
        )
        self.assertIsNone(final["input_decision"])
        self.assertTrue(final["workflow_guard"]["requires_input_approval"])
        self.assertEqual(nia_client.payloads, [])

    async def test_active_auto_output_becomes_shadowed_before_bitrix(self):
        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        store = MongoConnectorEventStore(InMemoryCollection())
        service = ConnectorIngestionService(store)
        nia_client = FakeNiaClient()
        bitrix_client = FakeBitrixClient()
        preflight, nia, _ = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_active_policy,
            start,
        )
        _, _, shadow_bitrix = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_shadow_policy,
            start,
        )

        received = await service.ingest(
            event_form(),
            self.settings_for(ConnectorMode.ACTIVE),
        )
        await preflight.run_once()
        await nia.run_once()
        shadowed = await shadow_bitrix.run_once()
        final = await store.get_by_key(received.event_key)

        self.assertEqual(shadowed.status, ConnectorWorkerRunStatus.COMPLETED)
        self.assertEqual(final["status"], ConnectorEventStatus.SHADOWED.value)
        self.assertFalse(final["workflow_guard"]["bitrix_send_allowed"])
        self.assertIsNone(final["outbound_message_id"])
        self.assertEqual(bitrix_client.payloads, [])

    async def test_active_blocked_preflight_stays_quarantined(self):
        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        store = MongoConnectorEventStore(InMemoryCollection())
        service = ConnectorIngestionService(store)
        nia_client = FakeNiaClient()
        bitrix_client = FakeBitrixClient()
        preflight, nia, _ = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_active_policy,
            start,
        )
        form = event_form()
        form["data[message][text]"] = "token=secretvalue123"

        received = await service.ingest(
            form,
            self.settings_for(ConnectorMode.ACTIVE),
        )
        await preflight.run_once()
        nia_result = await nia.run_once()
        final = await store.get_by_key(received.event_key)

        self.assertEqual(
            final["status"],
            ConnectorEventStatus.NEEDS_INPUT_REVIEW.value,
        )
        self.assertIsNone(final["input_decision"])
        self.assertIn(
            "possible_secret_detected",
            final["preflight_review"]["preflight_manifest"]["blocking_reasons"],
        )
        self.assertEqual(nia_result.status, ConnectorWorkerRunStatus.IDLE)
        self.assertEqual(nia_client.payloads, [])

    async def test_shadow_preserves_blocked_nia_output_as_terminal_evidence(self):
        class EmptyNiaClient:
            def __init__(self):
                self.payloads = []

            async def send_approved_text(self, payload):
                self.payloads.append(payload)
                return NiaClientResult.succeeded(
                    NiaChatResponse(respuesta=""),
                    http_status=200,
                )

        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        store = MongoConnectorEventStore(InMemoryCollection())
        service = ConnectorIngestionService(store)
        nia_client = EmptyNiaClient()
        bitrix_client = FakeBitrixClient()
        preflight, nia, bitrix = self.workers(
            store,
            nia_client,
            bitrix_client,
            enabled_shadow_policy,
            start,
        )

        received = await service.ingest(
            event_form(),
            self.settings_for(ConnectorMode.SHADOW),
        )
        await preflight.run_once()
        await nia.run_once()
        bitrix_result = await bitrix.run_once()
        final = await store.get_by_key(received.event_key)

        self.assertEqual(final["status"], ConnectorEventStatus.SHADOWED.value)
        self.assertEqual(final["nia_response"]["respuesta"], "")
        self.assertEqual(final["output_review"]["decision"], "blocked")
        self.assertIn(
            "empty_nia_response",
            final["output_review"]["blocking_reasons"],
        )
        self.assertEqual(bitrix_result.status, ConnectorWorkerRunStatus.IDLE)
        self.assertEqual(bitrix_client.payloads, [])


if __name__ == "__main__":
    unittest.main()
