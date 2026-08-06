import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m67_operational_audit import (
    M67_MISSING_OPERATIONAL_LINKS,
)
from bitrix_connector.bitrix_history_r0_m72_readiness_reaudit import (
    M72_CLOSED_LINKS,
    M72_FIXTURE_PREPARED_REAL_LINKS,
    M72_STILL_UNBOUND_LOGICAL_LINKS,
    reaudit_m67_after_m68_m71,
)


ROOT = Path(__file__).resolve().parents[1]


class M72ReadinessReauditTests(unittest.TestCase):
    def test_exact_nine_links_are_partitioned_without_overlap(self):
        audit = reaudit_m67_after_m68_m71()
        groups = (
            audit.closed_links,
            audit.fixture_prepared_real_links,
            audit.still_unbound_logical_links,
        )
        flattened = tuple(link for group in groups for link in group)

        self.assertEqual(len(flattened), 9)
        self.assertEqual(len(set(flattened)), 9)
        self.assertEqual(set(flattened), set(M67_MISSING_OPERATIONAL_LINKS))
        self.assertEqual((audit.closed_link_count, audit.fixture_prepared_real_link_count, audit.still_unbound_logical_link_count), (2, 4, 3))

    def test_closed_fixture_and_unbound_classifications_are_exact(self):
        audit = reaudit_m67_after_m68_m71()

        self.assertEqual(audit.closed_links, M72_CLOSED_LINKS)
        self.assertEqual(
            audit.fixture_prepared_real_links, M72_FIXTURE_PREPARED_REAL_LINKS
        )
        self.assertEqual(
            audit.still_unbound_logical_links, M72_STILL_UNBOUND_LOGICAL_LINKS
        )
        self.assertEqual(audit.formal_remaining_link_count, 7)
        self.assertEqual(
            audit.formal_remaining_links,
            tuple(
                link
                for link in M67_MISSING_OPERATIONAL_LINKS
                if link not in M72_CLOSED_LINKS
            ),
        )

    def test_linear_chain_needs_one_owner_not_another_adapter_layer(self):
        audit = reaudit_m67_after_m68_m71()

        self.assertEqual(audit.composition_chain, ("M68", "M69", "M70", "M71"))
        self.assertTrue(audit.composition_chain_linear)
        self.assertFalse(audit.redundant_new_adapter_layers_detected)
        self.assertFalse(audit.additional_fixture_adapter_layer_needed)
        self.assertEqual(
            audit.next_minimum_phase,
            "m73_single_owner_literal_attention_and_cleanup_fixture_only",
        )
        self.assertEqual(len(audit.minimum_remaining_phases), 3)

    def test_reaudit_remains_no_go_without_attention_or_authority(self):
        audit = reaudit_m67_after_m68_m71()

        self.assertEqual((audit.phase, audit.state), ("M72", "NO-GO"))
        for field in (
            "first_confirmation_request_ready",
            "point_8_can_begin",
            "human_attention_required_now",
            "message_request_authorized",
            "source_bound",
            "command_available",
            "real_execution_authorized",
            "actual_connection_proven",
            "persisted",
            "nia_next_called",
            "bitrix_written",
        ):
            self.assertFalse(getattr(audit, field), field)
        self.assertEqual(audit.external_calls, 0)
        self.assertTrue(audit.connector_locked_off)

    def test_partition_cannot_be_reduced_or_reclassified(self):
        audit = reaudit_m67_after_m68_m71()
        with self.assertRaises(ValueError):
            replace(audit, closed_links=audit.closed_links[:-1])
        with self.assertRaises(ValueError):
            replace(
                audit,
                fixture_prepared_real_links=(
                    *audit.fixture_prepared_real_links,
                    audit.still_unbound_logical_links[0],
                ),
            )

    def test_source_has_no_io_clients_commands_secrets_or_human_boundary(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m72_readiness_reaudit.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "access_token", "send_approved_", "delete_approved_",
            "read_post_", "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
