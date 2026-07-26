import unittest
from unittest.mock import Mock

from bitrix_connector.config import load_settings
from bitrix_connector.pilot_discovery_factory import (
    PilotDiscoveryConfigurationError,
    PilotDiscoveryOAuthFactory,
)


def complete_settings(**overrides):
    values = {
        "NIA_BITRIX_MONGO_URI": "mongodb://mongo.test",
        "NIA_BITRIX_MONGO_DB": "nia",
        "NIA_BITRIX_INSTALLATIONS_COLLECTION": "oauth_installations",
        "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
        "NIA_BITRIX_MEMBER_ID": "member-123",
        "NIA_BITRIX_CLIENT_ID": "local.client",
        "NIA_BITRIX_CLIENT_SECRET": "client-secret",
    }
    values.update(overrides)
    return load_settings(values)


class FakeMongoClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.closed = False

    def __getitem__(self, name):
        return self

    def close(self):
        self.closed = True


class PilotDiscoveryOAuthFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_only_oauth_resources_with_tz_aware_mongo(self):
        mongo = FakeMongoClient()
        transport = Mock()
        transport.close = unittest.mock.AsyncMock()
        provider = object()
        factory = PilotDiscoveryOAuthFactory(
            mongo_client_factory=Mock(return_value=mongo),
            oauth_transport_factory=Mock(return_value=transport),
            oauth_provider_factory=Mock(return_value=provider),
        )

        resources = await factory.build(
            complete_settings(),
            timeout_seconds=7,
        )

        self.assertIs(resources.oauth_provider, provider)
        self.assertEqual(
            resources.portal_url,
            "https://portal.bitrix24.test",
        )
        self.assertEqual(resources.member_id, "member-123")
        self.assertEqual(mongo.kwargs, {})
        factory._mongo_client_factory.assert_called_once_with(
            "mongodb://mongo.test",
            tz_aware=True,
        )
        await resources.close()
        transport.close.assert_awaited_once()
        self.assertTrue(mongo.closed)

    async def test_missing_identity_fails_before_creating_resources(self):
        mongo_factory = Mock()
        factory = PilotDiscoveryOAuthFactory(
            mongo_client_factory=mongo_factory
        )

        with self.assertRaisesRegex(
            PilotDiscoveryConfigurationError,
            "pilot_discovery_member_id_not_configured",
        ):
            await factory.build(
                complete_settings(NIA_BITRIX_MEMBER_ID=""),
                timeout_seconds=7,
            )

        mongo_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
