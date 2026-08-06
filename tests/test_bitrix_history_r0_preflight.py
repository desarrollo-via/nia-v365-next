import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0PreflightOutcome,
    build_bitrix_history_r0_preflight_from_dialog,
    execute_bitrix_history_r0_preflight_once,
)
from bitrix_connector.bitrix_history_r0_runner import BitrixHistoryR0Status
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]


def dialog(
    *,
    chat_id=78733,
    dialog_id=None,
    entity_type="LINES",
    role="guest",
    session_id=900,
    last_message_id=700,
):
    return BitrixHistoryDialog.model_validate({
        "id": chat_id,
        "dialog_id": dialog_id or f"chat{chat_id}",
        "entity_type": entity_type,
        "entity_data_1": f"a|b|c|d|e|{session_id}",
        "role": role,
        "last_message_id": last_message_id,
    })


class FakePreflightClient:
    def __init__(self, read_result=None, *, read_error=None, close_error=False):
        self.read_result = read_result
        self.read_error = read_error
        self.close_error = close_error
        self.dialog_calls = 0
        self.closed = False

    async def get_dialog(self, dialog_id):
        self.dialog_calls += 1
        if self.read_error is not None:
            raise self.read_error
        return self.read_result

    async def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("close failed")


def successful_read(value=None):
    return BitrixHistoryReadResult(
        decision=BitrixHistoryReadDecision.SUCCESS,
        dialog=value or dialog(),
        http_status=200,
    )


class BitrixHistoryR0PreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_preloaded_dialog_builds_same_anchor_without_client_or_read(self):
        outcome = build_bitrix_history_r0_preflight_from_dialog(
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            dialog=dialog(),
            resources_closed=True,
        )

        self.assertEqual(outcome.result.status, BitrixHistoryR0Status.READY)
        self.assertEqual(outcome.result.dialog_read_calls, 1)
        self.assertEqual(outcome.result.history_read_calls, 0)
        self.assertTrue(outcome.result.resources_closed)
        self.assertTrue(outcome.anchor_available)
        self.assertEqual(outcome.require_anchor().session_id, 900)

    async def test_ready_uses_one_read_and_keeps_anchor_out_of_public_output(self):
        client = FakePreflightClient(successful_read())
        factory_calls = 0

        async def factory():
            nonlocal factory_calls
            factory_calls += 1
            return client

        outcome = await execute_bitrix_history_r0_preflight_once(
            client_factory=factory,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
        )

        self.assertIsInstance(outcome, BitrixHistoryR0PreflightOutcome)
        self.assertEqual(outcome.result.status, BitrixHistoryR0Status.READY)
        self.assertEqual(outcome.result.reason, "bitrix_history_preflight_ready")
        self.assertEqual(factory_calls, 1)
        self.assertEqual(client.dialog_calls, 1)
        self.assertTrue(client.closed)
        self.assertEqual(outcome.result.dialog_read_calls, 1)
        self.assertEqual(outcome.result.history_read_calls, 0)
        self.assertEqual(outcome.result.mutation_calls, 0)
        self.assertTrue(outcome.result.dialog_verified)
        self.assertTrue(outcome.result.session_verified)
        self.assertTrue(outcome.result.baseline_captured)
        self.assertTrue(outcome.result.connector_locked_off)
        self.assertFalse(outcome.result.persisted)
        self.assertFalse(outcome.result.nia_called)
        self.assertFalse(outcome.result.bitrix_written)
        self.assertTrue(outcome.result.resources_closed)
        self.assertTrue(outcome.anchor_available)
        anchor = outcome.require_anchor()
        self.assertEqual(anchor.session_id, 900)
        self.assertEqual(anchor.baseline_last_message_id, 700)
        self.assertNotIn("900", repr(outcome))
        self.assertNotIn("700", repr(outcome))
        self.assertNotIn("900", repr(anchor))
        self.assertNotIn("700", repr(anchor))
        self.assertNotIn("session_id", outcome.result.model_dump())
        self.assertNotIn("baseline_last_message_id", outcome.result.model_dump())

    async def test_documented_owner_role_is_accepted_without_exposing_it(self):
        client = FakePreflightClient(successful_read(dialog(role="owner")))

        async def factory():
            return client

        outcome = await execute_bitrix_history_r0_preflight_once(
            client_factory=factory,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
        )

        self.assertEqual(outcome.result.status, BitrixHistoryR0Status.READY)
        self.assertTrue(outcome.anchor_available)
        self.assertIsNone(outcome.identity_diagnostic)
        self.assertNotIn("owner", repr(outcome))

    async def test_degraded_barrier_stops_before_creating_resources(self):
        factory_calls = 0

        async def factory():
            nonlocal factory_calls
            factory_calls += 1
            raise AssertionError("factory must not run")

        settings = load_settings({
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_PILOT_ENABLED": "true",
            "NIA_BITRIX_PILOT_EMERGENCY_STOP": "false",
            "NIA_BITRIX_PILOT_RULES_JSON": "[]",
        })
        outcome = await execute_bitrix_history_r0_preflight_once(
            client_factory=factory,
            settings=settings,
        )

        self.assertEqual(outcome.result.status, BitrixHistoryR0Status.NO_GO)
        self.assertEqual(outcome.result.reason, "bitrix_history_barrier_degraded")
        self.assertEqual(factory_calls, 0)
        self.assertEqual(outcome.result.dialog_read_calls, 0)
        self.assertTrue(outcome.result.resources_closed)
        self.assertFalse(outcome.anchor_available)

    async def test_mismatch_or_invalid_session_fails_closed(self):
        cases = (
            (successful_read(dialog(chat_id=78734)), "bitrix_history_dialog_mismatch"),
            (
                successful_read(BitrixHistoryDialog.model_validate({
                    "id": 78733,
                    "dialog_id": "chat78733",
                    "entity_type": "LINES",
                    "entity_data_1": "invalid-session-shape",
                    "role": "guest",
                    "last_message_id": 700,
                })),
                "bitrix_history_session_identity_invalid",
            ),
        )
        for read_result, reason in cases:
            with self.subTest(reason=reason):
                client = FakePreflightClient(read_result)

                async def factory():
                    return client

                outcome = await execute_bitrix_history_r0_preflight_once(
                    client_factory=factory,
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                )
                self.assertEqual(outcome.result.status, BitrixHistoryR0Status.NO_GO)
                self.assertEqual(outcome.result.reason, reason)
                self.assertEqual(client.dialog_calls, 1)
                self.assertTrue(client.closed)
                self.assertFalse(outcome.anchor_available)

    async def test_identity_mismatch_diagnostic_contains_only_four_booleans(self):
        cases = (
            (
                dialog(chat_id=78734, dialog_id="chat78733"),
                (False, True, True, True),
            ),
            (
                dialog(dialog_id="chat78734"),
                (True, False, True, True),
            ),
            (
                dialog(entity_type="OPENLINES"),
                (True, True, False, True),
            ),
            (
                dialog(role="   "),
                (True, True, True, False),
            ),
        )
        for mismatched_dialog, expected in cases:
            with self.subTest(expected=expected):
                client = FakePreflightClient(successful_read(mismatched_dialog))

                async def factory():
                    return client

                outcome = await execute_bitrix_history_r0_preflight_once(
                    client_factory=factory,
                    settings=load_settings({"NIA_BITRIX_MODE": "off"}),
                )
                diagnostic = outcome.identity_diagnostic
                self.assertIsNotNone(diagnostic)
                self.assertEqual(
                    (
                        diagnostic.chat_id_matches,
                        diagnostic.dialog_id_matches,
                        diagnostic.entity_type_matches,
                        diagnostic.role_allowed,
                    ),
                    expected,
                )
                self.assertEqual(diagnostic.mismatch_count, 1)
                serialized = repr(outcome) + repr(diagnostic)
                for forbidden in (
                    "78734",
                    "chat78734",
                    "OPENLINES",
                    "entity_data_1",
                ):
                    self.assertNotIn(forbidden, serialized)

    async def test_read_or_close_failure_is_terminal_and_redacted(self):
        read_client = FakePreflightClient(read_error=RuntimeError("secret body"))

        async def read_factory():
            return read_client

        read_outcome = await execute_bitrix_history_r0_preflight_once(
            client_factory=read_factory,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
        )
        self.assertEqual(read_outcome.result.reason, "bitrix_history_preflight_failed_safe")
        self.assertNotIn("secret body", repr(read_outcome))
        self.assertTrue(read_client.closed)

        close_client = FakePreflightClient(successful_read(), close_error=True)

        async def close_factory():
            return close_client

        close_outcome = await execute_bitrix_history_r0_preflight_once(
            client_factory=close_factory,
            settings=load_settings({"NIA_BITRIX_MODE": "off"}),
        )
        self.assertEqual(close_outcome.result.status, BitrixHistoryR0Status.NO_GO)
        self.assertEqual(
            close_outcome.result.reason,
            "bitrix_history_resources_close_failed",
        )
        self.assertFalse(close_outcome.result.resources_closed)
        self.assertFalse(close_outcome.anchor_available)

    async def test_cancellation_closes_resources_and_source_has_no_real_composition(self):
        client = FakePreflightClient(read_error=asyncio.CancelledError())

        async def factory():
            return client

        with self.assertRaises(asyncio.CancelledError):
            await execute_bitrix_history_r0_preflight_once(
                client_factory=factory,
                settings=load_settings({"NIA_BITRIX_MODE": "off"}),
            )
        self.assertTrue(client.closed)

        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_preflight.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "load_dotenv",
            "dotenv",
            "os.environ",
            "get_session_history(",
            "refresh_access_token",
            "imopenlines.session.history.get",
            "config.update",
            "event.bind",
            "im.v2.Event.subscribe",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
