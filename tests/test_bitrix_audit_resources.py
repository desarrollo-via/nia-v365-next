import unittest
from dataclasses import replace

from bitrix_connector.audit_resources import (
    AuditResourcesConfigurationError,
    ConnectorAuditReaderFactory,
)
from bitrix_connector.config import ConnectorMode, load_settings


class FakeMongoClient:
    def __init__(self, uri, **options):
        self.uri = uri
        self.options = options
        self.database_names = []
        self.close_calls = 0

    def __getitem__(self, name):
        self.database_names.append(name)
        return {"database": name}

    def close(self):
        self.close_calls += 1


class FakeAuditStore:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []
        self.ensure_indexes_calls = 0

    async def ensure_indexes(self):
        self.ensure_indexes_calls += 1
        raise AssertionError("audit_factory_must_not_create_indexes")

    async def list_audit_events(self, *, status=None, limit=50):
        self.calls.append(("list", status, limit))
        if self.error is not None:
            raise self.error
        return []

    async def get_audit_event(self, event_key):
        self.calls.append(("get", event_key))
        if self.error is not None:
            raise self.error
        return None


def configured_settings():
    return load_settings(
        {
            "NIA_BITRIX_REVIEW_TOKEN": "review-secret",
            "NIA_BITRIX_MONGO_URI": "mongodb://unused.invalid",
            "NIA_BITRIX_MONGO_DB": "nia_audit",
            "NIA_BITRIX_EVENTS_COLLECTION": "nia_bitrix_events",
        }
    )


class ConnectorAuditReaderFactoryTests(unittest.IsolatedAsyncioTestCase):
    def build_factory(self, store=None, store_error=None):
        clients = []
        stores = []

        def client_factory(uri, **options):
            client = FakeMongoClient(uri, **options)
            clients.append(client)
            return client

        def store_factory(database, collection_name):
            if store_error is not None:
                raise store_error
            selected = store or FakeAuditStore()
            stores.append((database, collection_name, selected))
            return selected

        return (
            ConnectorAuditReaderFactory(
                mongo_client_factory=client_factory,
                store_factory=store_factory,
            ),
            clients,
            stores,
        )

    async def test_off_mode_can_open_read_only_resources_and_closes_once(self):
        factory, clients, stores = self.build_factory()
        settings = configured_settings()

        self.assertEqual(settings.effective_mode, ConnectorMode.OFF)
        self.assertTrue(settings.activation_locked)
        self.assertFalse(settings.external_calls_enabled)

        resources = factory.open(settings)
        async with resources as reader:
            response = await reader.list_events(limit=1)

        self.assertEqual(response.returned, 0)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].uri, "mongodb://unused.invalid")
        self.assertEqual(clients[0].options, {"connect": False})
        self.assertEqual(clients[0].database_names, ["nia_audit"])
        self.assertEqual(stores[0][1], "nia_bitrix_events")
        self.assertEqual(stores[0][2].ensure_indexes_calls, 0)
        self.assertEqual(clients[0].close_calls, 1)

        resources.close()
        self.assertEqual(clients[0].close_calls, 1)

    async def test_query_failure_still_closes_ephemeral_client(self):
        store = FakeAuditStore(error=RuntimeError("simulated_store_failure"))
        factory, clients, _ = self.build_factory(store=store)
        resources = factory.open(configured_settings())

        with self.assertRaisesRegex(RuntimeError, "simulated_store_failure"):
            async with resources as reader:
                await reader.list_events()

        self.assertEqual(clients[0].close_calls, 1)
        self.assertEqual(store.ensure_indexes_calls, 0)

    async def test_partial_construction_failure_closes_client(self):
        factory, clients, _ = self.build_factory(
            store_error=RuntimeError("store_factory_failed")
        )

        with self.assertRaisesRegex(RuntimeError, "store_factory_failed"):
            factory.open(configured_settings())

        self.assertEqual(clients[0].close_calls, 1)

    async def test_missing_configuration_fails_before_motor_construction(self):
        cases = [
            (
                replace(configured_settings(), review_token=None),
                "audit_review_token_not_configured",
            ),
            (
                replace(configured_settings(), mongo_uri=None),
                "audit_mongo_uri_not_configured",
            ),
            (
                replace(configured_settings(), mongo_db=" "),
                "audit_mongo_db_not_configured",
            ),
            (
                replace(configured_settings(), events_collection=" "),
                "audit_events_collection_not_configured",
            ),
        ]

        for settings, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                factory, clients, stores = self.build_factory()
                with self.assertRaisesRegex(
                    AuditResourcesConfigurationError,
                    expected_code,
                ):
                    factory.open(settings)
                self.assertEqual(clients, [])
                self.assertEqual(stores, [])


if __name__ == "__main__":
    unittest.main()
