import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m63_literal_parser import (
    M63_FIRST_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_m71_rollback_factory_composition import (
    RollbackFactoryM70Composition,
)
from bitrix_connector.bitrix_history_r0_m73_single_fixture_owner import (
    InjectedFixtureAttentionEvidence,
    SingleFixtureR1Owner,
)
from bitrix_connector.bitrix_history_r0_m75_dormant_real_bindings import (
    DormantRealBindingOwner,
)
from bitrix_connector.bitrix_history_r0_m76_in_memory_concrete_builders import (
    InMemoryConcreteBindingBuilders,
    InMemoryConcreteBindingSettings,
)
from bitrix_connector.bitrix_history_r0_m78_single_sealed_owner import (
    SingleSealedM73M77Owner,
    SingleSealedOwnerStatus,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from tests.test_bitrix_history_r0_m70_sender_factory_composition import (
    HistoryReader,
    PostAnchorReader,
    inbound_payload,
    ready_owner,
)
from tests.test_bitrix_history_r0_m73_single_fixture_owner import (
    AttentionProbe,
    TextReader,
)
from tests.test_bitrix_history_r0_m75_dormant_real_bindings import OAuthFixture
from tests.test_bitrix_history_r0_m76_in_memory_concrete_builders import (
    MemoryHttpFactory,
)


ROOT = Path(__file__).resolve().parents[1]


async def m78_owner(*, text_reader=None, attention=None, http_factory=None):
    text_reader = text_reader or TextReader()
    attention = attention or AttentionProbe()
    http_factory = http_factory or MemoryHttpFactory()
    concrete = InMemoryConcreteBindingBuilders(
        settings=InMemoryConcreteBindingSettings(
            nia_base_url="https://nia.fixture.local",
            portal_url="https://bitrix.fixture.local",
            timeout_seconds=10,
        ),
        http_resource_factory=http_factory,
    )
    oauth = OAuthFixture()
    binding = DormantRealBindingOwner(
        oauth_loader=oauth,
        nia_builder=concrete.build_nia,
        bitrix_builder=concrete.build_bitrix,
        deleter_builder=concrete.build_deleter,
        history_builder=concrete.build_history,
        timeout_seconds=10,
    )
    preflight = await ready_owner(probed=False)
    exact = RollbackFactoryM70Composition(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=preflight,
        history_reader=PostAnchorReader(inbound_payload()),
        nia_sender_factory=binding.build_nia_sender_once,
        bitrix_sender_factory=binding.build_bitrix_sender_once,
        post_send_history_reader=HistoryReader(include_reply=False),
        deleter_factory=binding.build_deleter_once,
        post_delete_reader_factory=binding.build_post_delete_reader_once,
        expected_sender_id=51,
    )
    m73 = SingleFixtureR1Owner(
        plan=build_protected_real_roundtrip_plan(),
        text_reader=text_reader,
        preflight_adapter=preflight,
        attention_probe=attention,
        exact_scope_owner=exact,
        timeout_seconds=300,
    )
    owner = SingleSealedM73M77Owner(
        m73_owner=m73,
        binding_owner=binding,
        concrete_builders=concrete,
    )
    return owner, text_reader, attention, oauth, http_factory, m73, exact


class M78SingleSealedOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_owner_runs_literals_attention_and_sealed_rollback(self):
        owner, texts, attention, oauth, http_factory, m73, exact = await m78_owner()

        result = await owner.run_once()

        self.assertEqual(result.status, SingleSealedOwnerStatus.VERIFIED)
        self.assertEqual(result.literal_read_calls, 3)
        self.assertEqual(result.preflight_probe_calls, 1)
        self.assertEqual(result.attention_probe_calls, 1)
        self.assertEqual(result.exact_scope_owner_calls, 1)
        self.assertTrue(result.fixture_attention_boundary_verified)
        self.assertTrue(result.sealed_exact_scope_verified)
        self.assertTrue(result.sealed_rollback_verified)
        self.assertEqual(result.oauth_loader_calls, 1)
        self.assertEqual(result.oauth_refresh_calls, 0)
        self.assertEqual(result.concrete_builder_calls, 4)
        self.assertEqual((result.dependency_close_calls, result.http_close_calls), (4, 4))
        self.assertEqual((texts.calls, attention.calls), (3, 1))
        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))
        self.assertEqual(len(http_factory.requests), 4)
        self.assertTrue(all(client.is_closed for client in http_factory.clients))
        self.assertTrue(result.all_private_owners_closed)
        self.assertTrue(m73.cleared)
        self.assertTrue(exact.cleared)

    async def test_literal_rejection_builds_no_oauth_or_http_resource(self):
        reader = TextReader((M63_FIRST_CONFIRMATION_TEXT + " ",))
        owner, _, attention, oauth, http_factory, *_ = await m78_owner(
            text_reader=reader
        )

        result = await owner.run_once()

        self.assertEqual(result.status, SingleSealedOwnerStatus.NO_GO)
        self.assertEqual(result.literal_read_calls, 1)
        self.assertEqual(result.exact_scope_owner_calls, 0)
        self.assertEqual((oauth.calls, len(http_factory.calls)), (0, 0))
        self.assertEqual(attention.calls, 0)
        self.assertTrue(result.all_private_owners_closed)

    async def test_invalid_attention_stops_before_concrete_chain(self):
        attention = AttentionProbe(
            InjectedFixtureAttentionEvidence(
                fixture_message_signal_received=False
            )
        )
        owner, _, _, oauth, http_factory, *_ = await m78_owner(
            attention=attention
        )

        result = await owner.run_once()

        self.assertEqual(result.status, SingleSealedOwnerStatus.NO_GO)
        self.assertEqual(result.literal_read_calls, 3)
        self.assertEqual(result.attention_probe_calls, 1)
        self.assertEqual(result.exact_scope_owner_calls, 0)
        self.assertEqual((oauth.calls, len(http_factory.calls)), (0, 0))

    async def test_cancelled_literal_path_cleans_without_constructing_clients(self):
        reader = TextReader(error=asyncio.CancelledError())
        owner, _, _, oauth, http_factory, *_ = await m78_owner(text_reader=reader)

        result = await owner.run_once()

        self.assertEqual(result.status, SingleSealedOwnerStatus.CANCELLED)
        self.assertEqual((oauth.calls, len(http_factory.calls)), (0, 0))
        self.assertTrue(result.all_private_owners_closed)

    async def test_invalid_delete_receipt_is_no_go_and_closes_created_resources(self):
        http_factory = MemoryHttpFactory(invalid_delete=True)
        owner, _, _, oauth, _, *_ = await m78_owner(http_factory=http_factory)

        result = await owner.run_once()

        self.assertEqual(result.status, SingleSealedOwnerStatus.NO_GO)
        self.assertEqual(result.concrete_builder_calls, 3)
        self.assertEqual((result.dependency_close_calls, result.http_close_calls), (3, 3))
        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))
        self.assertTrue(all(client.is_closed for client in http_factory.clients))

    async def test_reuse_never_repeats_literals_oauth_or_http(self):
        owner, texts, _, oauth, http_factory, *_ = await m78_owner()
        first = await owner.run_once()

        second = await owner.run_once()

        self.assertEqual(first.status, SingleSealedOwnerStatus.VERIFIED)
        self.assertEqual(second.reason, "m78_reuse_rejected")
        self.assertEqual(texts.calls, 3)
        self.assertEqual(oauth.calls, 1)
        self.assertEqual(len(http_factory.requests), 4)

    async def test_result_is_redacted_and_keeps_real_boundaries_false(self):
        owner, *_ = await m78_owner()

        result = await owner.run_once()
        rendered = result.model_dump_json()

        for forbidden in (
            "PRIMERA CONFIRMACIÓN",
            "WAITING-MESSAGE",
            "373259",
            "78733",
            "fixture inbound",
            "fixture reply",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertFalse(result.fixture_masquerade_used)
        self.assertFalse(result.network_capable_resources_accepted)
        self.assertFalse(result.real_authorizations_consumed)
        self.assertFalse(result.first_confirmation_request_ready)
        self.assertFalse(result.human_attention_required_now)
        self.assertFalse(result.source_bound)
        self.assertFalse(result.command_available)

    def test_source_has_no_real_source_command_service_or_attention_effect(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m78_single_sealed_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "httpx", "pymongo", "argparse", "input(", "subprocess",
            "socket", "pilotdiscoveryoauthfactory(", "get_access_token(",
            "refresh_access_token(", "waiting-message", "print(", "toast",
            "messagebox",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
