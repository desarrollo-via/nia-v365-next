import unittest
from pathlib import Path

from bitrix_connector.r1_integral_v2_review_session_factory import (
    ExactR1ReviewSessionClientFactory,
    PUBLIC_ORIGIN,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_owner import (
    REVIEW_TOKEN_NAME,
)


class Source:
    def __init__(self, path):
        self.path = path
        self.calls = []

    async def open(self):
        self.calls.append("open")

    async def read_exact(self, name):
        self.calls.append(("read", name))
        return bytearray(b"review-token-fixture-1234567890")

    async def close(self):
        self.calls.append("close")


class ReviewSessionFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_allowlisted_read_builds_one_redacted_client(self):
        sources = []
        clients = []

        def source_builder(path):
            source = Source(path)
            sources.append(source)
            return source

        def client_builder(**kwargs):
            clients.append(kwargs)
            return object()

        factory = ExactR1ReviewSessionClientFactory(
            dotenv_path=Path(".env"),
            source_builder=source_builder,
            client_builder=client_builder,
        )
        result = await factory()

        self.assertIs(result.__class__, object)
        self.assertEqual(sources[0].calls, [
            "open", ("read", REVIEW_TOKEN_NAME), "close"
        ])
        self.assertEqual(clients[0]["public_origin"], PUBLIC_ORIGIN)
        self.assertEqual(
            clients[0]["review_token"],
            "review-token-fixture-1234567890",
        )
        with self.assertRaisesRegex(RuntimeError, "reused"):
            await factory()


if __name__ == "__main__":
    unittest.main()
