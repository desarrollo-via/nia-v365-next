import asyncio
import unittest
from pathlib import Path

import httpx

from bitrix_connector.bitrix_client import BitrixClient
from bitrix_connector.bitrix_history_r0_client import BitrixHistoryR0Client
from bitrix_connector.bitrix_history_r0_m76_in_memory_concrete_builders import (
    ExactReplyDeleteClient,
)
from bitrix_connector.bitrix_history_r0_m86_real_https_factory import (
    M86HttpsClientSettings,
    M86RealHttpsClientFactory,
    M86_HTTPS_BINDING_NAMES,
    M86_HTTPS_TIMEOUT_SECONDS,
    build_real_m86_https_client_factory,
    inspect_m86_https_binding,
)
from bitrix_connector.nia_client import NiaClient


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-m86-b-private-token"


class HermeticAsyncClientFactory:
    def __init__(self, *, fail_name=None, cancel_name=None):
        self.fail_name = fail_name
        self.cancel_name = cancel_name
        self.calls = []
        self.clients = []
        self.requests = []

    async def __call__(self, name, timeout_seconds):
        self.calls.append((name, timeout_seconds))
        if name == self.fail_name:
            raise RuntimeError("private factory failure")
        if name == self.cancel_name:
            raise asyncio.CancelledError()

        async def handler(request):
            self.requests.append(request)
            raise AssertionError("no request is allowed in M86-B")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout_seconds,
        )
        self.clients.append(client)
        return client


class CloseFailAsyncClient(httpx.AsyncClient):
    def __init__(self):
        super().__init__(transport=httpx.MockTransport(lambda _request: httpx.Response(500)))
        self.close_calls = 0

    async def aclose(self):
        self.close_calls += 1
        await super().aclose()
        raise RuntimeError("private close failure")


def factory(http_factory=None):
    http_factory = http_factory or HermeticAsyncClientFactory()
    value = M86RealHttpsClientFactory(
        settings=M86HttpsClientSettings(
            nia_base_url="https://nia.fixture.invalid",
            portal_url="https://bitrix.fixture.invalid",
        ),
        http_client_factory=http_factory,
    )
    return value, http_factory


class M86RealHttpsClientFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_m83_concrete_client_types_build_once_without_requests(self):
        value, http_factory = factory()

        built = (
            await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS),
            await value.build_bitrix(TOKEN, M86_HTTPS_TIMEOUT_SECONDS),
            await value.build_deleter(TOKEN, M86_HTTPS_TIMEOUT_SECONDS),
            await value.build_history(TOKEN, M86_HTTPS_TIMEOUT_SECONDS),
        )
        snapshot = await value.close()

        self.assertEqual(
            tuple(type(item.dependency) for item in built),
            (NiaClient, BitrixClient, ExactReplyDeleteClient, BitrixHistoryR0Client),
        )
        self.assertEqual(
            tuple(name for name, _timeout in http_factory.calls),
            M86_HTTPS_BINDING_NAMES,
        )
        self.assertEqual(http_factory.requests, [])
        self.assertEqual(snapshot.status, "VERIFIED")
        self.assertEqual(snapshot.http_client_factory_calls, 4)
        self.assertEqual(snapshot.concrete_clients_constructed, 4)
        self.assertEqual((snapshot.dependency_close_calls, snapshot.http_close_calls), (4, 4))
        self.assertEqual(snapshot.requests_executed, 0)
        self.assertTrue(all(client.is_closed for client in http_factory.clients))

    async def test_each_builder_is_one_shot_and_reuse_makes_factory_terminal(self):
        value, http_factory = factory()

        await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS)
        with self.assertRaisesRegex(RuntimeError, "nia_https_builder_rejected"):
            await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS)
        snapshot = await value.close()

        self.assertEqual(len(http_factory.calls), 1)
        self.assertEqual(snapshot.status, "NO-GO")
        self.assertEqual(snapshot.retry_budget, 0)
        self.assertTrue(http_factory.clients[0].is_closed)

    async def test_third_factory_failure_is_terminal_and_closes_prior_resources(self):
        http_factory = HermeticAsyncClientFactory(fail_name="deleter")
        value, _ = factory(http_factory)

        await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS)
        await value.build_bitrix(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)
        with self.assertRaisesRegex(RuntimeError, "private factory failure"):
            await value.build_deleter(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)
        with self.assertRaisesRegex(RuntimeError, "history_https_builder_rejected"):
            await value.build_history(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)
        snapshot = await value.close()

        self.assertEqual(tuple(name for name, _ in http_factory.calls), ("nia", "bitrix", "deleter"))
        self.assertEqual(snapshot.status, "NO-GO")
        self.assertEqual(snapshot.http_client_factory_calls, 3)
        self.assertEqual((snapshot.dependency_close_calls, snapshot.http_close_calls), (2, 2))
        self.assertTrue(all(client.is_closed for client in http_factory.clients))

    async def test_cancellation_is_terminal_and_cleanup_remains_available(self):
        http_factory = HermeticAsyncClientFactory(cancel_name="bitrix")
        value, _ = factory(http_factory)

        await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS)
        with self.assertRaises(asyncio.CancelledError):
            await value.build_bitrix(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)
        snapshot = await value.close()

        self.assertEqual(tuple(name for name, _ in http_factory.calls), ("nia", "bitrix"))
        self.assertEqual(snapshot.status, "NO-GO")
        self.assertEqual(snapshot.dependency_close_calls, 1)
        self.assertTrue(http_factory.clients[0].is_closed)

    async def test_wrong_factory_result_is_rejected_without_retry(self):
        calls = []

        async def wrong_factory(name, timeout_seconds):
            calls.append((name, timeout_seconds))
            return object()

        value, _ = factory(wrong_factory)
        with self.assertRaisesRegex(TypeError, "factory_result_invalid"):
            await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS)
        snapshot = await value.close()

        self.assertEqual(len(calls), 1)
        self.assertEqual(snapshot.status, "NO-GO")
        self.assertEqual(snapshot.retry_budget, 0)

    async def test_close_failure_is_visible_and_all_four_cleanups_are_attempted(self):
        calls = []
        clients = []

        async def close_factory(name, timeout_seconds):
            calls.append((name, timeout_seconds))
            client = (
                CloseFailAsyncClient()
                if name == "bitrix"
                else httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda _request: httpx.Response(500)
                    )
                )
            )
            clients.append(client)
            return client

        value, _ = factory(close_factory)
        await value.build_nia(M86_HTTPS_TIMEOUT_SECONDS)
        await value.build_bitrix(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)
        await value.build_deleter(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)
        await value.build_history(TOKEN, M86_HTTPS_TIMEOUT_SECONDS)

        snapshot = await value.close()

        self.assertEqual(snapshot.status, "NO-GO")
        self.assertEqual((snapshot.dependency_close_calls, snapshot.http_close_calls), (4, 4))
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(client.is_closed for client in clients))
        self.assertEqual(clients[1].close_calls, 1)

    def test_invalid_origins_and_timeout_fail_before_http_factory(self):
        for url in (
            "http://fixture.invalid",
            "https://user@fixture.invalid",
            "https://fixture.invalid/path",
            "https://fixture.invalid?query=1",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "https_origin_invalid"):
                    M86HttpsClientSettings(nia_base_url=url, portal_url="https://ok.invalid")
        with self.assertRaisesRegex(ValueError, "https_timeout_invalid"):
            M86HttpsClientSettings(
                nia_base_url="https://nia.invalid",
                portal_url="https://bitrix.invalid",
                timeout_seconds=11,
            )

    def test_real_factory_is_lazy_and_contract_reports_zero_open_or_requests(self):
        value = build_real_m86_https_client_factory(
            nia_base_url="https://nia.fixture.invalid",
            portal_url="https://bitrix.fixture.invalid",
        )
        self.assertIsInstance(value, M86RealHttpsClientFactory)
        self.assertEqual(value._owned, [])
        self.assertEqual(value._http_factory_calls, 0)

        snapshot = inspect_m86_https_binding()
        self.assertEqual((snapshot.phase, snapshot.state), ("M86-B", "BOUND-NOT-OPENED"))
        self.assertEqual(snapshot.binding_names, M86_HTTPS_BINDING_NAMES)
        self.assertEqual((snapshot.client_budget, snapshot.retry_budget), (4, 0))
        self.assertEqual((snapshot.real_clients_constructed, snapshot.real_requests_executed), (0, 0))
        self.assertEqual(snapshot.remaining_real_bindings, 3)
        self.assertFalse(snapshot.resources_opened)
        self.assertFalse(snapshot.attention_required_now)

    def test_repr_and_source_expose_no_source_command_or_test_transport(self):
        value, _ = factory()
        self.assertEqual(repr(value), "M86RealHttpsClientFactory(<redacted>)")
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_real_https_factory.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "mocktransport",
            ".env",
            "dotenv",
            "os.environ",
            "credentialmanager",
            "pymongo",
            "motor",
            "refresh_access_token(",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
