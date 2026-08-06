import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m63_literal_parser import (
    M63_FIRST_CONFIRMATION_TEXT,
    M63_MANUAL_REMOVAL_TEXT,
    M63_SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_m71_rollback_factory_composition import (
    RollbackFactoryM70Composition,
)
from bitrix_connector.bitrix_history_r0_m73_single_fixture_owner import (
    InjectedFixtureAttentionEvidence,
    SingleFixtureR1Owner,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from tests.test_bitrix_history_r0_m70_sender_factory_composition import (
    HistoryReader,
    PostAnchorReader,
    default_factories,
    inbound_payload,
    ready_owner,
)
from tests.test_bitrix_history_r0_m71_rollback_factory_composition import (
    DeleteDependency,
    ReadDependency,
    RollbackFactory,
)


ROOT = Path(__file__).resolve().parents[1]
EXACT_TEXTS = (
    M63_FIRST_CONFIRMATION_TEXT,
    M63_MANUAL_REMOVAL_TEXT,
    M63_SECOND_CONFIRMATION_TEXT,
)


class TextReader:
    def __init__(self, values=EXACT_TEXTS, *, error=None, block=False):
        self.values = list(values)
        self.error = error
        self.block = block
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.block:
            await asyncio.Event().wait()
        return self.values.pop(0)


class AttentionProbe:
    def __init__(self, value=None, *, error=None):
        self.value = value or InjectedFixtureAttentionEvidence()
        self.error = error
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


async def owner_fixture(
    *,
    text_reader=None,
    attention=None,
    bot_id=373259,
    timeout_seconds=300,
):
    text_reader = text_reader or TextReader()
    attention = attention or AttentionProbe()
    preflight = await ready_owner(probed=False, bot_id=bot_id)
    nia_factory, bitrix_factory = default_factories()
    exact = RollbackFactoryM70Composition(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=preflight,
        history_reader=PostAnchorReader(inbound_payload()),
        nia_sender_factory=nia_factory,
        bitrix_sender_factory=bitrix_factory,
        post_send_history_reader=HistoryReader(include_reply=True),
        deleter_factory=RollbackFactory(DeleteDependency()),
        post_delete_reader_factory=RollbackFactory(ReadDependency()),
        expected_sender_id=51,
    )
    owner = SingleFixtureR1Owner(
        plan=build_protected_real_roundtrip_plan(),
        text_reader=text_reader,
        preflight_adapter=preflight,
        attention_probe=attention,
        exact_scope_owner=exact,
        timeout_seconds=timeout_seconds,
    )
    return owner, text_reader, preflight, attention, exact, nia_factory, bitrix_factory


class SingleFixtureR1OwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_owner_composes_literals_preflight_attention_and_exact_scope(self):
        items = await owner_fixture()
        owner, texts, preflight, attention, exact, nia, bitrix = items

        result = await owner.run_once()

        self.assertEqual(result.state, "PREPARED")
        self.assertEqual(result.literal_read_calls, 3)
        self.assertEqual(result.preflight_probe_calls, 1)
        self.assertEqual(result.attention_probe_calls, 1)
        self.assertEqual(result.exact_scope_owner_calls, 1)
        self.assertTrue(result.fixture_attention_boundary_verified)
        self.assertTrue(result.exact_scope_verified_in_fixtures)
        self.assertEqual(result.fixture_authorizations_consumed, 3)
        self.assertEqual((texts.calls, attention.calls), (3, 1))
        self.assertEqual((nia.calls, bitrix.calls), (1, 1))
        self.assertTrue(preflight.cleared)
        self.assertTrue(exact.cleared)
        self.assertTrue(owner.cleared)
        rendered = result.model_dump_json()
        for private in ("PRIMERA CONFIRMACIÓN", "WAITING-MESSAGE", "78733", "373259"):
            self.assertNotIn(private, rendered)

    async def test_literal_rejection_stops_before_preflight_attention_and_chain(self):
        reader = TextReader((M63_FIRST_CONFIRMATION_TEXT + " ",))
        items = await owner_fixture(text_reader=reader)
        owner, _, preflight, attention, exact, nia, bitrix = items

        result = await owner.run_once()

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.literal_read_calls, 1)
        self.assertEqual(result.preflight_probe_calls, 0)
        self.assertEqual(attention.calls, 0)
        self.assertEqual((nia.calls, bitrix.calls), (0, 0))
        self.assertTrue(preflight.cleared)
        self.assertTrue(exact.cleared)

    async def test_preflight_drift_stops_before_attention_and_chain(self):
        items = await owner_fixture(bot_id=999999)
        owner, _, _, attention, _, nia, bitrix = items

        result = await owner.run_once()

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.preflight_probe_calls, 1)
        self.assertEqual(result.literal_read_calls, 1)
        self.assertEqual(attention.calls, 0)
        self.assertEqual((nia.calls, bitrix.calls), (0, 0))

    async def test_invalid_attention_stops_before_exact_scope(self):
        invalid = InjectedFixtureAttentionEvidence(
            fixture_message_signal_received=False
        )
        attention = AttentionProbe(invalid)
        items = await owner_fixture(attention=attention)
        owner, _, _, _, exact, nia, bitrix = items

        result = await owner.run_once()

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.literal_read_calls, 3)
        self.assertEqual(result.attention_probe_calls, 1)
        self.assertEqual(result.exact_scope_owner_calls, 0)
        self.assertEqual((nia.calls, bitrix.calls), (0, 0))
        self.assertTrue(exact.cleared)

    async def test_timeout_and_cancellation_are_terminal_and_clean(self):
        cases = (
            (TextReader(block=True), 0.01, "NO-GO"),
            (TextReader(error=asyncio.CancelledError()), 300, "CANCELLED"),
        )
        for reader, timeout, state in cases:
            with self.subTest(state=state):
                owner, _, preflight, attention, exact, nia, bitrix = (
                    await owner_fixture(
                        text_reader=reader, timeout_seconds=timeout
                    )
                )
                result = await owner.run_once()
                self.assertEqual(result.state, state)
                self.assertEqual(attention.calls, 0)
                self.assertEqual((nia.calls, bitrix.calls), (0, 0))
                self.assertTrue(preflight.cleared)
                self.assertTrue(exact.cleared)
                self.assertTrue(owner.cleared)

    async def test_reuse_performs_no_second_read_probe_or_chain_call(self):
        owner, texts, _, attention, _, nia, bitrix = await owner_fixture()
        await owner.run_once()
        result = await owner.run_once()

        self.assertEqual(result.reason, "m73_single_owner_reuse_rejected")
        self.assertEqual((texts.calls, attention.calls), (3, 1))
        self.assertEqual((nia.calls, bitrix.calls), (1, 1))

    def test_source_has_no_real_sources_clients_commands_or_attention_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m73_single_fixture_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "access_token", "print(", "toast", "messagebox",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
