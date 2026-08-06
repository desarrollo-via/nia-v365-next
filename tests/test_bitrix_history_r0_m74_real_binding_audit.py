import inspect
import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_client import BitrixClient
from bitrix_connector.bitrix_history_r0_client import BitrixHistoryR0Client
from bitrix_connector.bitrix_history_r0_m70_sender_factory_composition import (
    InjectedFixtureSenderResource,
)
from bitrix_connector.bitrix_history_r0_m71_rollback_factory_composition import (
    InjectedFixtureRollbackResource,
)
from bitrix_connector.bitrix_history_r0_m74_real_binding_audit import (
    M74_REAL_LINKS,
    audit_real_bindings_after_m73,
)
from bitrix_connector.nia_client import NiaClient


ROOT = Path(__file__).resolve().parents[1]


class M74RealBindingAuditTests(unittest.TestCase):
    def test_exact_four_real_links_are_mapped_once(self):
        audit = audit_real_bindings_after_m73()
        self.assertEqual(audit.links, M74_REAL_LINKS)
        self.assertEqual(
            {item.link for item in audit.links},
            {
                "nia_sender",
                "bitrix_sender",
                "exact_reply_deleter",
                "post_delete_history_reader",
            },
        )
        self.assertEqual(len(audit.links), len({item.link for item in audit.links}))

    def test_existing_sender_signatures_match_injected_protocols(self):
        nia = inspect.signature(NiaClient.send_approved_text)
        bitrix = inspect.signature(BitrixClient.send_approved_message)
        self.assertEqual(tuple(nia.parameters), ("self", "payload"))
        self.assertEqual(tuple(bitrix.parameters), ("self", "payload"))
        self.assertTrue(audit_real_bindings_after_m73().links[0].method_signature_matches)
        self.assertTrue(audit_real_bindings_after_m73().links[1].method_signature_matches)

    def test_history_candidate_needs_method_and_shape_adapter(self):
        history = inspect.signature(BitrixHistoryR0Client.get_session_history)
        self.assertEqual(tuple(history.parameters), ("self", "session_id"))
        link = audit_real_bindings_after_m73().links[3]
        self.assertFalse(link.method_signature_matches)
        self.assertIn("typed_history_to_rollback_mapping", link.missing_binding)

    def test_delete_has_contract_but_no_concrete_client_binding(self):
        link = audit_real_bindings_after_m73().links[2]
        self.assertEqual(link.candidate, "ReplyRollbackDeletePreview")
        self.assertFalse(link.method_signature_matches)
        self.assertFalse(link.close_owner_identified)
        self.assertIn("exact_http_reply_deleter", link.missing_binding)

    def test_m70_m71_resource_contracts_are_fixture_only(self):
        for resource in (InjectedFixtureSenderResource, InjectedFixtureRollbackResource):
            signature = inspect.signature(resource)
            self.assertIs(signature.parameters["fixture_only"].default, True)
            self.assertIs(signature.parameters["real_client_constructed"].default, False)
        audit = audit_real_bindings_after_m73()
        self.assertTrue(audit.m70_m71_accept_fixture_resources_only)
        self.assertEqual(audit.directly_compatible_link_count, 0)

    def test_shared_oauth_close_timeout_and_budgets_remain_mandatory(self):
        audit = audit_real_bindings_after_m73()
        self.assertTrue(audit.shared_stored_oauth_owner_required)
        self.assertEqual((audit.stored_oauth_get_budget, audit.oauth_refresh_budget), (1, 0))
        self.assertEqual(audit.maximum_http_timeout_seconds, 10)
        self.assertTrue(audit.every_resource_close_required)
        self.assertTrue(all(item.call_budget == 1 and item.retry_budget == 0 for item in audit.links))

    def test_audit_stays_no_go_without_attention_or_resource_construction(self):
        audit = audit_real_bindings_after_m73()
        self.assertEqual((audit.phase, audit.state), ("M74", "NO-GO"))
        for field in (
            "first_confirmation_request_ready",
            "point_8_can_begin",
            "human_attention_required_now",
            "message_request_authorized",
            "resources_constructed",
            "source_bound",
            "command_available",
            "real_execution_authorized",
            "persisted",
            "nia_next_called",
            "bitrix_written",
        ):
            self.assertFalse(getattr(audit, field), field)
        self.assertEqual(audit.external_calls, 0)
        self.assertTrue(audit.connector_locked_off)
        with self.assertRaises(ValueError):
            replace(audit, links=audit.links[:-1])

    def test_ledger_source_has_no_io_client_construction_or_human_boundary(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_m74_real_binding_audit.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "bitrixhistoryr0client(", "pilotdiscoveryoauthfactory(",
            "get_access_token(",
            "refresh_access_token(", "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
