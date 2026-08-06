import unittest
from pathlib import Path

from pydantic import ValidationError

from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    ProtectedRealRoundtripPlan,
    build_protected_real_roundtrip_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class ProtectedRealRoundtripPlanTests(unittest.TestCase):
    def test_plan_distinguishes_local_rollback_from_real_verification(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertEqual(plan.phase, "M56")
        self.assertEqual(plan.reconciled_phase, "M64")
        self.assertEqual(plan.state, "NO-GO")
        self.assertEqual(
            plan.reason,
            "real_roundtrip_plan_blocked_confirmations_and_real_binding_missing",
        )
        self.assertTrue(plan.rollback_method_locally_implemented)
        self.assertTrue(plan.rollback_contract_locally_tested)
        self.assertTrue(plan.rollback_verified_in_doubles)
        self.assertFalse(plan.rollback_verified)
        self.assertTrue(plan.execution_blocked_until_rollback_verified)

    def test_scope_is_only_controlled_chat_and_bot(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertEqual(plan.target_dialog_id, "chat78733")
        self.assertEqual(plan.controlled_bot_id, 373259)
        self.assertEqual(plan.production_bot_id, 245339)
        self.assertTrue(plan.same_dialog_reply_required)
        self.assertTrue(plan.production_bot_must_remain_untouched)
        self.assertEqual(plan.openline_config_mutation_budget, 0)
        self.assertEqual(plan.bot_registration_mutation_budget, 0)
        self.assertEqual(plan.route_assignment_binding_mutation_budget, 0)
        self.assertEqual(plan.wazzup_mutation_budget, 0)

    def test_preflight_and_roundtrip_budgets_are_bounded(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertEqual(plan.preflight_revision_read_budget, 1)
        self.assertEqual(plan.preflight_bot_list_read_budget, 1)
        self.assertEqual(plan.preflight_openline_config_read_budget, 1)
        self.assertEqual(plan.preflight_dialog_read_budget, 1)
        self.assertEqual(plan.baseline_history_read_budget, 1)
        self.assertEqual(plan.post_send_history_read_budget, 1)
        self.assertEqual(plan.nia_call_budget, 1)
        self.assertEqual(plan.bitrix_reply_send_budget, 1)
        self.assertEqual(plan.rollback_delete_call_budget, 1)
        self.assertEqual(plan.post_delete_history_read_budget, 1)
        self.assertEqual(plan.retry_budget, 0)
        self.assertEqual(plan.maximum_window_seconds, 180)

    def test_initial_filter_priority_is_explicit(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertTrue(plan.objective_first_isolated_connection)
        self.assertTrue(plan.minimum_filter_only)
        self.assertTrue(plan.exact_text_hash_filter_deferred)
        self.assertTrue(plan.exact_time_window_filter_deferred)
        self.assertTrue(plan.require_single_human_candidate_after_baseline)

    def test_success_and_rollback_receipts_are_explicit(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertTrue(plan.require_send_receipt_message_id)
        self.assertTrue(plan.require_sent_message_in_same_dialog)
        self.assertTrue(plan.rollback_target_must_derive_from_send_receipt)
        self.assertTrue(plan.rollback_must_remove_only_sent_reply)
        self.assertTrue(plan.rollback_must_reverify_same_dialog_absence)

    def test_generic_sp_is_not_a_production_authorization(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertTrue(plan.first_precise_confirmation_required)
        self.assertTrue(plan.second_precise_confirmation_required)
        self.assertFalse(plan.first_precise_confirmation_present)
        self.assertFalse(plan.second_precise_confirmation_present)
        self.assertFalse(plan.m63_confirmation_drafts_consumable)
        self.assertFalse(plan.generic_sp_authorizes_production_write)
        self.assertFalse(plan.real_execution_authorized)

    def test_m63_drafts_cannot_claim_confirmation_or_real_authority(self):
        plan = build_protected_real_roundtrip_plan()

        for update in (
            {"m63_confirmation_drafts_consumable": True},
            {"first_precise_confirmation_present": True},
            {"second_precise_confirmation_present": True},
            {"real_execution_authorized": True},
            {"rollback_verified": True},
        ):
            with self.subTest(update=update):
                with self.assertRaises(ValidationError):
                    ProtectedRealRoundtripPlan.model_validate(
                        {**plan.model_dump(), **update}
                    )

    def test_build_has_no_calls_effects_or_attention_request(self):
        plan = build_protected_real_roundtrip_plan()

        self.assertFalse(plan.command_available)
        self.assertFalse(plan.cli_available)
        self.assertFalse(plan.source_bound)
        self.assertFalse(plan.human_message_required_now)
        self.assertFalse(plan.attention_required_now)
        self.assertEqual(plan.external_calls, 0)
        self.assertTrue(plan.connector_locked_off)
        self.assertFalse(plan.persisted)
        self.assertFalse(plan.nia_next_called)
        self.assertFalse(plan.bitrix_written)
        self.assertFalse(plan.actual_connection_proven)

    def test_contract_is_frozen_strict_and_cannot_claim_go(self):
        plan = build_protected_real_roundtrip_plan()

        with self.assertRaises(ValidationError):
            ProtectedRealRoundtripPlan.model_validate(
                {**plan.model_dump(), "state": "GO"}
            )
        with self.assertRaises(ValidationError):
            ProtectedRealRoundtripPlan.model_validate(
                {**plan.model_dump(), "extra": True}
            )
        with self.assertRaises(ValidationError):
            ProtectedRealRoundtripPlan.model_validate(
                {**plan.model_dump(), "external_calls": 1}
            )
        with self.assertRaises(ValidationError):
            plan.state = "GO"

    def test_source_has_no_execution_or_integration_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_real_roundtrip_plan.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "niaclient(",
            "bitrixclient(",
            "send_approved_text(",
            "send_approved_message(",
            ".open(",
            "dotenv",
            "os.environ",
            "get_dialog(",
            "get_session_history(",
            "asyncio.run",
            "httpx",
            "pymongo",
            "subprocess",
            "socket",
            "argparse",
            "config.update",
            "insert_one",
            "update_one",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
