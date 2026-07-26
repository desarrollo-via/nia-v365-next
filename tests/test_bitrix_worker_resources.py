import unittest
from types import SimpleNamespace

from bitrix_connector.config import ConnectorMode, load_settings
from bitrix_connector.worker_resources import (
    ConnectorWorkerResourcesFactory,
    WorkerResourceOptions,
    WorkerResourcesConfigurationError,
)


class FakeCollection:
    def __init__(self, name, log):
        self.name = name
        self.log = log

    async def create_index(self, keys, **kwargs):
        self.log.append(("index", self.name, kwargs["name"]))
        return kwargs["name"]


class FakeDatabase:
    def __init__(self, log):
        self.log = log
        self.collections = {}

    def __getitem__(self, name):
        self.log.append(("collection", name))
        return self.collections.setdefault(name, FakeCollection(name, self.log))


class FakeMongoClient:
    def __init__(self, uri, log):
        self.uri = uri
        self.log = log
        self.database = FakeDatabase(log)
        self.closed = False

    def __getitem__(self, name):
        self.log.append(("database", name))
        return self.database

    def close(self):
        self.closed = True
        self.log.append(("close", "mongo"))


class FakeAsyncResource:
    def __init__(self, name, log, **kwargs):
        self.name = name
        self.log = log
        self.kwargs = kwargs
        self.close_count = 0

    async def close(self):
        self.close_count += 1
        self.log.append(("close", self.name))


class FakeComposition:
    pass


def enabled_settings(**changes):
    values = {
        "activation_locked": False,
        "effective_mode": ConnectorMode.REVIEW,
        "external_calls_enabled": True,
        "mongo_uri": "mongodb://example.invalid",
        "mongo_db": "nia_worker",
        "events_collection": "events",
        "installations_collection": "installations",
        "nia_base_url": "https://nia.example.test",
        "bitrix_domain": "portal.bitrix24.test",
        "bitrix_member_id": "member-1",
        "bitrix_client_id": "client-id",
        "bitrix_client_secret": "client-secret",
    }
    values.update(changes)
    return SimpleNamespace(**values)


class WorkerResourcesFactoryTests(unittest.IsolatedAsyncioTestCase):
    def options(self):
        return WorkerResourceOptions(worker_id="worker-test")

    async def test_real_settings_are_inert_before_any_constructor(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("no debe construirse ningún recurso")

        factory = ConnectorWorkerResourcesFactory(
            mongo_client_factory=forbidden,
            nia_client_factory=forbidden,
            oauth_transport_factory=forbidden,
            oauth_provider_factory=forbidden,
            bitrix_client_factory=forbidden,
            composition_factory=forbidden,
        )

        resources = await factory.build(
            load_settings({"NIA_BITRIX_MODE": "active"}),
            self.options(),
        )

        self.assertIsNone(resources)
        self.assertEqual(calls, [])

    async def test_each_safety_barrier_blocks_before_mongo(self):
        for changes in (
            {"activation_locked": True},
            {"effective_mode": ConnectorMode.OFF},
            {"external_calls_enabled": False},
        ):
            with self.subTest(changes=changes):
                calls = []
                factory = ConnectorWorkerResourcesFactory(
                    mongo_client_factory=lambda uri, **options: calls.append(uri),
                )
                resources = await factory.build(
                    enabled_settings(**changes),
                    self.options(),
                )
                self.assertIsNone(resources)
                self.assertEqual(calls, [])

    async def test_missing_configuration_fails_before_mongo(self):
        fields = {
            "mongo_uri": "worker_mongo_uri_not_configured",
            "nia_base_url": "worker_nia_base_url_not_configured",
            "bitrix_client_secret": "worker_bitrix_client_secret_not_configured",
        }
        for field, error in fields.items():
            with self.subTest(field=field):
                calls = []
                factory = ConnectorWorkerResourcesFactory(
                    mongo_client_factory=lambda uri, **options: calls.append(uri),
                )
                with self.assertRaisesRegex(
                    WorkerResourcesConfigurationError,
                    error,
                ):
                    await factory.build(
                        enabled_settings(**{field: None}),
                        self.options(),
                    )
                self.assertEqual(calls, [])

    async def test_invalid_urls_fail_before_mongo(self):
        cases = (
            (
                {"nia_base_url": "https://user:secret@nia.example.test"},
                "worker_nia_base_url_invalid",
            ),
            (
                {"nia_base_url": "https://nia.example.test/nia/chat"},
                "worker_nia_base_url_invalid",
            ),
            (
                {"bitrix_domain": "http://portal.bitrix24.test"},
                "worker_bitrix_domain_invalid",
            ),
            (
                {"bitrix_domain": "portal.bitrix24.test/rest"},
                "worker_bitrix_domain_invalid",
            ),
        )
        for changes, error in cases:
            with self.subTest(changes=changes):
                calls = []
                factory = ConnectorWorkerResourcesFactory(
                    mongo_client_factory=lambda uri, **options: calls.append(uri),
                )
                with self.assertRaisesRegex(
                    WorkerResourcesConfigurationError,
                    error,
                ):
                    await factory.build(
                        enabled_settings(**changes),
                        self.options(),
                    )
                self.assertEqual(calls, [])

    async def test_builds_one_resource_graph_and_closes_in_reverse_order_once(self):
        log = []
        clients = {}

        def mongo_factory(uri, **options):
            self.assertEqual(options, {"tz_aware": True})
            clients["mongo"] = FakeMongoClient(uri, log)
            return clients["mongo"]

        def nia_factory(**kwargs):
            clients["nia"] = FakeAsyncResource("nia", log, **kwargs)
            return clients["nia"]

        def transport_factory(**kwargs):
            clients["oauth"] = FakeAsyncResource("oauth", log, **kwargs)
            return clients["oauth"]

        def provider_factory(store, transport):
            clients["provider"] = (store, transport)
            return "provider"

        def bitrix_factory(**kwargs):
            clients["bitrix"] = FakeAsyncResource("bitrix", log, **kwargs)
            return clients["bitrix"]

        composition_calls = []

        def composition_factory(store, nia, bitrix, **kwargs):
            composition_calls.append((store, nia, bitrix, kwargs))
            return FakeComposition()

        factory = ConnectorWorkerResourcesFactory(
            mongo_client_factory=mongo_factory,
            nia_client_factory=nia_factory,
            oauth_transport_factory=transport_factory,
            oauth_provider_factory=provider_factory,
            bitrix_client_factory=bitrix_factory,
            composition_factory=composition_factory,
        )
        options = WorkerResourceOptions(
            worker_id="worker-local",
            lease_seconds=17,
            default_retry_after_seconds=23,
            http_timeout_seconds=4.5,
        )

        resources = await factory.build(enabled_settings(), options)

        self.assertIsNotNone(resources)
        self.assertEqual(clients["mongo"].uri, "mongodb://example.invalid")
        self.assertEqual(clients["nia"].kwargs["base_url"], "https://nia.example.test")
        self.assertEqual(clients["bitrix"].kwargs["portal_url"], "https://portal.bitrix24.test")
        self.assertEqual(clients["bitrix"].kwargs["token_provider"], "provider")
        self.assertEqual(composition_calls[0][3]["worker_id"], "worker-local")
        self.assertEqual(composition_calls[0][3]["lease_seconds"], 17)
        self.assertIn("pilot_policy_provider", composition_calls[0][3])
        self.assertGreaterEqual(
            len([entry for entry in log if entry[0] == "index"]),
            4,
        )

        await resources.close()
        await resources.close()

        self.assertEqual(
            [entry for entry in log if entry[0] == "close"],
            [
                ("close", "bitrix"),
                ("close", "oauth"),
                ("close", "nia"),
                ("close", "mongo"),
            ],
        )

    async def test_partial_construction_failure_closes_owned_resources(self):
        log = []
        mongo = FakeMongoClient("mongodb://example.invalid", log)
        nia = FakeAsyncResource("nia", log)

        def fail_transport(**kwargs):
            raise RuntimeError("transport construction failed")

        factory = ConnectorWorkerResourcesFactory(
            mongo_client_factory=lambda uri, **options: mongo,
            nia_client_factory=lambda **kwargs: nia,
            oauth_transport_factory=fail_transport,
        )

        with self.assertRaisesRegex(RuntimeError, "transport construction failed"):
            await factory.build(enabled_settings(), self.options())

        self.assertEqual(nia.close_count, 1)
        self.assertTrue(mongo.closed)


if __name__ == "__main__":
    unittest.main()
