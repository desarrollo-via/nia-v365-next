import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from bitrix_connector.bitrix_history_r0_preflight_composition import (
    execute_stored_oauth_history_preflight_once,
)
from bitrix_connector.bitrix_history_r0_runner import BitrixHistoryR0Status
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "oauth-secret-token"


def successful_read():
    return BitrixHistoryReadResult(
        decision=BitrixHistoryReadDecision.SUCCESS,
        dialog=BitrixHistoryDialog.model_validate({
            "id": 78733,
            "dialog_id": "chat78733",
            "entity_type": "LINES",
            "entity_data_1": "a|b|c|d|e|900",
            "role": "guest",
            "last_message_id": 700,
        }),
        http_status=200,
    )


class FakeProvider:
    def __init__(self, *, error=None):
        self.error = error
        self.get_calls = []
        self.refresh_calls = 0

    async def get_access_token(self, member_id):
        self.get_calls.append(member_id)
        if self.error is not None:
            raise self.error
        return TOKEN

    async def refresh_access_token(self, *_args):
        self.refresh_calls += 1
        raise AssertionError("refresh must not run")


class FakeResources:
    def __init__(self, provider=None, *, close_error=False):
        self.oauth_provider = provider or FakeProvider()
        self.portal_url = "https://portal.bitrix24.test"
        self.member_id = "member-protected"
        self.close_error = close_error
        self.closed = False

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("resource close secret")


class FakeResourcesFactory:
    def __init__(self, resources):
        self.resources = resources
        self.calls = []

    async def build(self, settings, *, timeout_seconds):
        self.calls.append((settings, timeout_seconds))
        return self.resources


class FakeClient:
    def __init__(self, *, close_error=False):
        self.close_error = close_error
        self.dialog_calls = 0
        self.closed = False

    async def get_dialog(self, dialog_id):
        self.dialog_calls += 1
        return successful_read()

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("client close secret")


class BitrixHistoryR0PreflightCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_composes_one_stored_token_read_and_closes_everything(self):
        resources = FakeResources()
        factory = FakeResourcesFactory(resources)
        client = FakeClient()
        build_calls = []

        def client_builder(**kwargs):
            build_calls.append(kwargs)
            return client

        outcome = await execute_stored_oauth_history_preflight_once(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            resources_factory=factory,
            client_builder=client_builder,
        )

        self.assertEqual(outcome.result.status, BitrixHistoryR0Status.READY)
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(factory.calls[0][1], 10.0)
        self.assertEqual(resources.oauth_provider.get_calls, [resources.member_id])
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(len(build_calls), 1)
        self.assertEqual(build_calls[0], {
            "portal_url": resources.portal_url,
            "access_token": TOKEN,
            "timeout_seconds": 10.0,
        })
        self.assertEqual(client.dialog_calls, 1)
        self.assertTrue(client.closed)
        self.assertTrue(resources.closed)
        self.assertTrue(outcome.result.resources_closed)
        self.assertNotIn(TOKEN, repr(outcome))
        self.assertNotIn(resources.member_id, repr(outcome))

    async def test_barrier_or_timeout_stops_before_oauth_resources(self):
        resources = FakeResources()
        factory = FakeResourcesFactory(resources)
        degraded = load_settings({
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_PILOT_ENABLED": "true",
            "NIA_BITRIX_PILOT_EMERGENCY_STOP": "false",
            "NIA_BITRIX_PILOT_RULES_JSON": "[]",
        })
        barrier = await execute_stored_oauth_history_preflight_once(
            settings=degraded,
            resources_factory=factory,
        )
        timeout = await execute_stored_oauth_history_preflight_once(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            timeout_seconds=10.1,
            resources_factory=factory,
        )

        self.assertEqual(barrier.result.reason, "bitrix_history_barrier_degraded")
        self.assertEqual(timeout.result.reason, "bitrix_history_timeout_invalid")
        self.assertEqual(factory.calls, [])
        self.assertFalse(resources.closed)

    async def test_token_or_builder_failure_closes_resources_without_details(self):
        cases = (
            (FakeResources(FakeProvider(error=RuntimeError("token secret"))), None),
            (FakeResources(), RuntimeError("builder secret")),
        )
        for resources, builder_error in cases:
            with self.subTest(builder_error=builder_error is not None):
                factory = FakeResourcesFactory(resources)

                def client_builder(**_kwargs):
                    if builder_error is not None:
                        raise builder_error
                    raise AssertionError("builder must not run")

                outcome = await execute_stored_oauth_history_preflight_once(
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                    resources_factory=factory,
                    client_builder=client_builder,
                )
                self.assertEqual(
                    outcome.result.reason,
                    "bitrix_history_preflight_failed_safe",
                )
                self.assertTrue(outcome.result.resources_closed)
                self.assertTrue(resources.closed)
                self.assertFalse(outcome.anchor_available)
                self.assertNotIn("secret", repr(outcome))

    async def test_any_close_failure_discards_anchor_and_is_terminal(self):
        cases = (
            (FakeResources(close_error=True), FakeClient()),
            (FakeResources(), FakeClient(close_error=True)),
        )
        for resources, client in cases:
            with self.subTest(resource_close_error=resources.close_error):
                outcome = await execute_stored_oauth_history_preflight_once(
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                    resources_factory=FakeResourcesFactory(resources),
                    client_builder=lambda **_kwargs: client,
                )
                self.assertEqual(outcome.result.status, BitrixHistoryR0Status.NO_GO)
                self.assertEqual(
                    outcome.result.reason,
                    "bitrix_history_resources_close_failed",
                )
                self.assertFalse(outcome.result.resources_closed)
                self.assertFalse(outcome.anchor_available)
                self.assertTrue(client.closed)
                self.assertTrue(resources.closed)

        setup_resources = FakeResources(
            FakeProvider(error=RuntimeError("token secret")),
            close_error=True,
        )
        setup_outcome = await execute_stored_oauth_history_preflight_once(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            resources_factory=FakeResourcesFactory(setup_resources),
        )
        self.assertEqual(
            setup_outcome.result.reason,
            "bitrix_history_resources_close_failed",
        )
        self.assertFalse(setup_outcome.result.resources_closed)
        self.assertFalse(setup_outcome.anchor_available)
        self.assertNotIn("secret", repr(setup_outcome))

    async def test_cancellation_closes_resources_and_source_forbids_expansion(self):
        provider = FakeProvider(error=asyncio.CancelledError())
        resources = FakeResources(provider)
        with self.assertRaises(asyncio.CancelledError):
            await execute_stored_oauth_history_preflight_once(
                settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                resources_factory=FakeResourcesFactory(resources),
            )
        self.assertTrue(resources.closed)

        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_preflight_composition.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "load_dotenv",
            "dotenv",
            "os.environ",
            "refresh_access_token",
            "get_session_history(",
            "imopenlines.session.history.get",
            "config.update",
            "event.bind",
            "im.v2.Event.subscribe",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
