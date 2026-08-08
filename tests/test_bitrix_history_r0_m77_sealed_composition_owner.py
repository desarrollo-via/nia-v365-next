import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m70_sender_factory_composition import (
    SenderFactoryCompositionStatus,
)
from bitrix_connector.bitrix_history_r0_m71_rollback_factory_composition import (
    RollbackFactoryCompositionStatus,
    RollbackFactoryM70Composition,
)
from bitrix_connector.bitrix_history_r0_m75_dormant_real_bindings import (
    DormantRealBindingOwner,
)
from bitrix_connector.bitrix_history_r0_m77_protected_resources import (
    InjectedSealedInMemoryRollbackResource,
    InjectedSealedInMemorySenderResource,
    ProtectedBindingClass,
)
from bitrix_connector.bitrix_history_r0_m77_sealed_composition_owner import (
    SealedCompositionStatus,
    SealedInMemoryM75M76Owner,
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
from tests.test_bitrix_history_r0_m71_rollback_factory_composition import (
    composition as fixture_composition,
)
from tests.test_bitrix_history_r0_m75_dormant_real_bindings import OAuthFixture
from tests.test_bitrix_history_r0_m76_in_memory_concrete_builders import (
    builders as concrete_builders,
)


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-private-token-m77"


async def sealed_owner(*, preserve_reply=False):
    concrete, http_factory = concrete_builders()
    oauth = OAuthFixture()
    binding = DormantRealBindingOwner(
        oauth_loader=oauth,
        nia_builder=concrete.build_nia,
        bitrix_builder=concrete.build_bitrix,
        deleter_builder=concrete.build_deleter,
        history_builder=concrete.build_history,
        timeout_seconds=10,
    )
    composition = RollbackFactoryM70Composition(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=await ready_owner(),
        history_reader=PostAnchorReader(inbound_payload()),
        nia_sender_factory=binding.build_nia_sender_once,
        bitrix_sender_factory=binding.build_bitrix_sender_once,
        post_send_history_reader=HistoryReader(include_reply=preserve_reply),
        deleter_factory=binding.build_deleter_once,
        post_delete_reader_factory=binding.build_post_delete_reader_once,
        expected_sender_id=51,
    )
    owner = SealedInMemoryM75M76Owner(
        composition=composition,
        binding_owner=binding,
        concrete_builders=concrete,
    )
    return owner, oauth, http_factory


class M77SealedCompositionOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_m75_m76_run_through_m70_m71_as_sealed_in_memory(self):
        owner, oauth, http_factory = await sealed_owner()

        result = await owner.run_once()

        self.assertEqual(result.status, SealedCompositionStatus.VERIFIED)
        self.assertEqual(
            result.binding_class,
            ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE.value,
        )
        self.assertEqual(result.oauth_loader_calls, 1)
        self.assertEqual(result.oauth_refresh_calls, 0)
        self.assertEqual(result.concrete_builder_calls, 4)
        self.assertEqual((result.dependency_close_calls, result.http_close_calls), (4, 4))
        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))
        self.assertEqual(len(http_factory.requests), 4)
        self.assertTrue(all(client.is_closed for client in http_factory.clients))
        self.assertTrue(result.all_private_owners_closed)
        self.assertFalse(result.fixture_masquerade_used)

    async def test_m71_reports_sealed_class_without_claiming_fixture(self):
        concrete, _ = concrete_builders()
        binding = DormantRealBindingOwner(
            oauth_loader=OAuthFixture(),
            nia_builder=concrete.build_nia,
            bitrix_builder=concrete.build_bitrix,
            deleter_builder=concrete.build_deleter,
            history_builder=concrete.build_history,
            timeout_seconds=10,
        )
        composition = RollbackFactoryM70Composition(
            plan=build_protected_real_roundtrip_plan(),
            preflight_adapter=await ready_owner(),
            history_reader=PostAnchorReader(inbound_payload()),
            nia_sender_factory=binding.build_nia_sender_once,
            bitrix_sender_factory=binding.build_bitrix_sender_once,
            post_send_history_reader=HistoryReader(include_reply=False),
            deleter_factory=binding.build_deleter_once,
            post_delete_reader_factory=binding.build_post_delete_reader_once,
            expected_sender_id=51,
        )

        result = await composition.run_once()
        await binding.close()
        await concrete.close()

        self.assertEqual(result.status, RollbackFactoryCompositionStatus.ROLLED_BACK)
        self.assertEqual(result.binding_class, "sealed-in-memory-concrete")
        self.assertFalse(result.fixture_only)
        self.assertTrue(result.concrete_clients_constructed_in_memory)
        self.assertFalse(result.network_capable_resources_accepted)

    async def test_legacy_fixture_path_remains_fixture_and_unchanged(self):
        composition, *_ = await fixture_composition()

        result = await composition.run_once()

        self.assertEqual(result.status, RollbackFactoryCompositionStatus.ROLLED_BACK)
        self.assertEqual(result.binding_class, "fixture-double")
        self.assertTrue(result.fixture_only)
        self.assertFalse(result.concrete_clients_constructed_in_memory)

    async def test_preserved_reply_keeps_rollback_lazy_and_m77_no_go(self):
        owner, oauth, http_factory = await sealed_owner(preserve_reply=True)

        result = await owner.run_once()

        self.assertEqual(result.status, SealedCompositionStatus.NO_GO)
        self.assertEqual(result.concrete_builder_calls, 2)
        self.assertEqual(len(http_factory.requests), 2)
        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))
        self.assertTrue(result.all_private_owners_closed)

    async def test_owner_reuse_does_not_repeat_any_client_or_oauth_call(self):
        owner, oauth, http_factory = await sealed_owner()
        first = await owner.run_once()

        second = await owner.run_once()

        self.assertEqual(first.status, SealedCompositionStatus.VERIFIED)
        self.assertEqual(second.status, SealedCompositionStatus.NO_GO)
        self.assertEqual(second.reason, "m77_reuse_rejected")
        self.assertEqual(oauth.calls, 1)
        self.assertEqual(len(http_factory.requests), 4)

    def test_network_capable_or_ambiguous_envelopes_are_rejected(self):
        async def close():
            return None

        with self.assertRaises(ValueError):
            InjectedSealedInMemorySenderResource(
                sender=object(), close_callback=close, network_capable=True
            )
        with self.assertRaises(ValueError):
            InjectedSealedInMemoryRollbackResource(
                dependency=object(),
                close_callback=close,
                transport_in_memory_only=False,
            )

    def test_binding_class_has_only_two_non_network_values(self):
        self.assertEqual(
            {item.value for item in ProtectedBindingClass},
            {"fixture-double", "sealed-in-memory-concrete"},
        )

    async def test_public_result_is_redacted_and_keeps_m73_disconnected(self):
        owner, _, _ = await sealed_owner()

        result = await owner.run_once()
        rendered = result.model_dump_json()

        for forbidden in (TOKEN, "373259", "78733", "fixture inbound", "fixture reply"):
            self.assertNotIn(forbidden, rendered)
        self.assertFalse(result.m73_connected)
        self.assertFalse(result.first_confirmation_request_ready)
        self.assertFalse(result.human_attention_required_now)
        self.assertFalse(result.source_bound)
        self.assertFalse(result.command_available)

    def test_source_has_no_real_source_command_or_m73_import(self):
        owner_source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m77_sealed_composition_owner.py"
        ).read_text(encoding="utf-8").lower()
        resource_source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m77_protected_resources.py"
        ).read_text(encoding="utf-8").lower()
        combined = owner_source + resource_source
        for forbidden in (
            ".env", "httpx", "pymongo", "argparse", "input(", "subprocess",
            "socket", "pilotdiscoveryoauthfactory(", "get_access_token(",
            "refresh_access_token(", "waiting-message",
            "bitrix_history_r0_m73_single_fixture_owner",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
