import unittest

from bitrix_connector.r1_key_vault_pre_event_oauth_builder import (
    build_dormant_key_vault_pre_event_lease_factory,
)
from tests.test_bitrix_event_scoped_r1_protected_oauth_builder import (
    CredentialBackend,
    ResourcesFactory,
    safety,
)


class KeyVaultPreEventBuilderTests(unittest.TestCase):
    def test_construction_and_lease_are_inert_and_receive_exact_url(self):
        credential = CredentialBackend()
        resources = ResourcesFactory()
        urls = []

        def backend_builder(*, vault_url):
            urls.append(vault_url)
            return credential

        factory = build_dormant_key_vault_pre_event_lease_factory(
            safety=safety(),
            vault_url="https://nia-next-r1-kv-260810.vault.azure.net",
            protected_backend_builder=backend_builder,
            resources_factory_builder=lambda: resources,
        )
        lease = factory()

        self.assertIsNotNone(lease)
        self.assertEqual(
            urls, ["https://nia-next-r1-kv-260810.vault.azure.net"]
        )
        self.assertEqual(credential.fetch_calls, 0)
        self.assertEqual(resources.build_calls, 0)


if __name__ == "__main__":
    unittest.main()
