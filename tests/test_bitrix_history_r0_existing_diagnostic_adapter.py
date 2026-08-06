import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
    BitrixSessionHistory,
)
from bitrix_connector.bitrix_history_r0_existing_diagnostic_adapter import (
    InjectedExistingHistoryDiagnosticAdapter,
    compose_injected_existing_history_diagnostic_adapter,
)
from bitrix_connector.bitrix_history_r0_existing_diagnostic_owner import (
    ExistingHistoryDiagnosticState,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "private-token-value"


def dialog():
    return BitrixHistoryDialog.model_validate(
        {
            "id": 78733,
            "dialog_id": "chat78733",
            "entity_type": "LINES",
            "entity_data_1": "a|b|c|d|e|900",
            "role": "guest",
            "last_message_id": 700,
        }
    )


def history():
    return BitrixSessionHistory.model_validate(
        {
            "chatId": 78733,
            "sessionId": 900,
            "message": [],
            "users": [],
        }
    )


class FakeProvider:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.refresh_calls = 0

    async def get_access_token(self, member_id):
        self.calls.append(member_id)
        if self.error is not None:
            raise self.error
        return TOKEN

    async def refresh_access_token(self, *_args):
        self.refresh_calls += 1
        raise AssertionError("refresh must not run")


class FakeResources:
    def __init__(self, provider=None, *, close_error=False, label="resource"):
        self.oauth_provider = provider or FakeProvider()
        self.portal_url = f"https://{label}.invalid"
        self.member_id = f"{label}-private-member"
        self.close_error = close_error
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_error:
            raise RuntimeError("private resource close detail")


class FakeFactory:
    def __init__(self, resources):
        self.resources = resources
        self.calls = []

    async def build(self, settings, *, timeout_seconds):
        self.calls.append((settings, timeout_seconds))
        return self.resources


class FakeClient:
    def __init__(self, *, dialog_result=None, history_result=None, close_error=False):
        self.dialog_result = dialog_result
        self.history_result = history_result
        self.close_error = close_error
        self.dialog_calls = []
        self.history_calls = []
        self.close_calls = 0

    async def get_dialog(self, dialog_id):
        self.dialog_calls.append(dialog_id)
        return self.dialog_result

    async def get_session_history(self, session_id):
        self.history_calls.append(session_id)
        return self.history_result

    async def close(self):
        self.close_calls += 1
        if self.close_error:
            raise RuntimeError("private client close detail")


def success_dialog():
    return BitrixHistoryReadResult(
        decision=BitrixHistoryReadDecision.SUCCESS,
        dialog=dialog(),
    )


def success_history():
    return BitrixHistoryReadResult(
        decision=BitrixHistoryReadDecision.SUCCESS,
        history=history(),
    )


class ExistingHistoryDiagnosticAdapterTests(unittest.IsolatedAsyncioTestCase):
    def build_adapter(
        self,
        *,
        preflight_resources=None,
        history_resources=None,
        preflight_client=None,
        history_client=None,
    ):
        preflight_resources = preflight_resources or FakeResources(label="preflight")
        history_resources = history_resources or FakeResources(label="history")
        preflight_client = preflight_client or FakeClient(
            dialog_result=success_dialog()
        )
        history_client = history_client or FakeClient(
            history_result=success_history()
        )
        clients = [preflight_client, history_client]
        builder_calls = []

        def client_builder(**kwargs):
            builder_calls.append(kwargs)
            return clients.pop(0)

        adapter = compose_injected_existing_history_diagnostic_adapter(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            timeout_seconds=4,
            preflight_resources_factory=FakeFactory(preflight_resources),
            history_resources_factory=FakeFactory(history_resources),
            client_builder=client_builder,
        )
        return (
            adapter,
            preflight_resources,
            history_resources,
            preflight_client,
            history_client,
            builder_calls,
        )

    async def test_prepared_mode_creates_nothing_and_does_not_consume_adapter(self):
        adapter, pre_resources, history_resources, pre_client, history_client, calls = (
            self.build_adapter()
        )

        preview = await adapter()
        result = await adapter(execute=True)

        self.assertEqual(preview.state, ExistingHistoryDiagnosticState.PREPARED)
        self.assertEqual(preview.dialog_read_calls, 0)
        self.assertEqual(preview.history_read_calls, 0)
        self.assertEqual(result.state, ExistingHistoryDiagnosticState.DIAGNOSED)
        self.assertEqual(len(calls), 2)
        self.assertEqual(pre_client.dialog_calls, ["chat78733"])
        self.assertEqual(history_client.history_calls, [900])
        self.assertEqual(pre_resources.close_calls, 1)
        self.assertEqual(history_resources.close_calls, 1)

    async def test_uses_two_separate_resources_and_each_token_once(self):
        adapter, pre_resources, history_resources, pre_client, history_client, calls = (
            self.build_adapter()
        )

        result = await adapter(execute=True)

        self.assertEqual(result.state, ExistingHistoryDiagnosticState.DIAGNOSED)
        self.assertEqual(result.dialog_read_calls, 1)
        self.assertEqual(result.history_read_calls, 1)
        self.assertEqual(pre_resources.oauth_provider.calls, [pre_resources.member_id])
        self.assertEqual(
            history_resources.oauth_provider.calls,
            [history_resources.member_id],
        )
        self.assertEqual(pre_resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(history_resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(pre_client.close_calls, 1)
        self.assertEqual(history_client.close_calls, 1)
        self.assertEqual(pre_resources.close_calls, 1)
        self.assertEqual(history_resources.close_calls, 1)
        self.assertEqual(len(calls), 2)
        serialized = result.model_dump_json()
        for forbidden in (
            TOKEN,
            pre_resources.member_id,
            history_resources.member_id,
            pre_resources.portal_url,
            history_resources.portal_url,
            "session_id",
            "message",
        ):
            self.assertNotIn(forbidden, serialized)

    async def test_adapter_is_one_shot_after_execution(self):
        adapter, *_ = self.build_adapter()

        first = await adapter(execute=True)
        second = await adapter(execute=True)

        self.assertEqual(first.state, ExistingHistoryDiagnosticState.DIAGNOSED)
        self.assertEqual(second.state, ExistingHistoryDiagnosticState.NO_GO)
        self.assertEqual(second.reason, "bitrix_history_existing_adapter_already_used")
        self.assertEqual(second.dialog_read_calls, 0)
        self.assertEqual(second.history_read_calls, 0)

    async def test_structural_history_failure_reaches_public_category(self):
        history_client = FakeClient(
            history_result=BitrixHistoryReadResult(
                decision=BitrixHistoryReadDecision.FAIL,
                error_code="bitrix_history_invalid_collections",
            )
        )
        adapter, *rest = self.build_adapter(history_client=history_client)

        result = await adapter(execute=True)

        self.assertEqual(result.state, ExistingHistoryDiagnosticState.NO_GO)
        self.assertEqual(result.failure_category, "reader_history_collections_invalid")
        self.assertEqual(result.history_read_calls, 1)
        self.assertTrue(result.resources_closed)
        self.assertNotIn("private", result.model_dump_json())
        self.assertTrue(rest)

    async def test_history_factory_failure_reports_verified_close(self):
        history_resources = FakeResources(
            FakeProvider(RuntimeError("private token detail")),
            label="history",
        )
        adapter, _, _, _, _, _ = self.build_adapter(
            history_resources=history_resources
        )

        result = await adapter(execute=True)

        self.assertEqual(result.reason, "bitrix_history_read_failed")
        self.assertEqual(result.failure_category, "reader_history_unavailable")
        self.assertEqual(result.history_read_calls, 0)
        self.assertTrue(result.resources_closed)
        self.assertEqual(history_resources.close_calls, 1)
        self.assertNotIn("private", result.model_dump_json())

    async def test_history_factory_close_failure_is_terminal(self):
        history_resources = FakeResources(
            FakeProvider(RuntimeError("private token detail")),
            close_error=True,
            label="history",
        )
        adapter, _, _, _, _, _ = self.build_adapter(
            history_resources=history_resources
        )

        result = await adapter(execute=True)

        self.assertEqual(result.reason, "bitrix_history_resources_close_failed")
        self.assertEqual(result.failure_category, "reader_resources_close_failed")
        self.assertFalse(result.resources_closed)
        self.assertEqual(result.history_read_calls, 0)
        self.assertNotIn("private", result.model_dump_json())

    async def test_cancellation_closes_partial_history_resource(self):
        history_resources = FakeResources(
            FakeProvider(asyncio.CancelledError()),
            label="history",
        )
        adapter, _, _, _, _, _ = self.build_adapter(
            history_resources=history_resources
        )

        with self.assertRaises(asyncio.CancelledError):
            await adapter(execute=True)
        self.assertEqual(history_resources.close_calls, 1)

    def test_composition_requires_injected_dependencies_and_has_no_real_surface(self):
        cases = (
            {
                "preflight_resources_factory": FakeFactory(FakeResources()),
                "history_resources_factory": FakeFactory(FakeResources()),
                "client_builder": None,
            },
            {
                "preflight_resources_factory": None,
                "history_resources_factory": FakeFactory(FakeResources()),
                "client_builder": lambda **_kwargs: None,
            },
            {
                "preflight_resources_factory": FakeFactory(FakeResources()),
                "history_resources_factory": None,
                "client_builder": lambda **_kwargs: None,
            },
        )
        for dependencies in cases:
            with self.subTest(dependencies=dependencies), self.assertRaises(TypeError):
                compose_injected_existing_history_diagnostic_adapter(
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                    timeout_seconds=4,
                    **dependencies,
                )

        adapter, *_ = self.build_adapter()
        self.assertIs(type(adapter), InjectedExistingHistoryDiagnosticAdapter)
        self.assertEqual(
            repr(adapter),
            "InjectedExistingHistoryDiagnosticAdapter(<redacted>)",
        )

        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_existing_diagnostic_adapter.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "PilotDiscoveryOAuthFactory",
            "BitrixHistoryR0Client",
            "dotenv",
            "os.environ",
            "waiting-message",
            "send_message",
            "input(",
            "asyncio.run",
            "httpx.",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "config.update",
            "refresh_access_token(",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
