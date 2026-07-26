import unittest

from bitrix_connector.config import ConnectorMode
from bitrix_connector.workflow_policy import (
    WorkflowGuard,
    WorkflowInputAction,
    WorkflowOutputAction,
)


class WorkflowGuardTests(unittest.TestCase):
    def test_mode_matrix(self):
        review = WorkflowGuard.from_mode(ConnectorMode.REVIEW)
        shadow = WorkflowGuard.from_mode(ConnectorMode.SHADOW)
        active = WorkflowGuard.from_mode(ConnectorMode.ACTIVE)

        self.assertTrue(review.requires_input_approval)
        self.assertTrue(review.requires_output_approval)
        self.assertTrue(review.bitrix_send_allowed)
        self.assertFalse(shadow.requires_input_approval)
        self.assertFalse(shadow.requires_output_approval)
        self.assertFalse(shadow.bitrix_send_allowed)
        self.assertFalse(active.requires_input_approval)
        self.assertFalse(active.requires_output_approval)
        self.assertTrue(active.bitrix_send_allowed)

    def test_restrictions_are_monotonic_and_active_cannot_restore_them(self):
        guard = WorkflowGuard.from_mode(ConnectorMode.ACTIVE)
        reviewed = guard.observe(ConnectorMode.REVIEW)
        shadowed = reviewed.observe(ConnectorMode.SHADOW)
        restored = shadowed.observe(ConnectorMode.ACTIVE)

        self.assertTrue(restored.requires_input_approval)
        self.assertTrue(restored.requires_output_approval)
        self.assertFalse(restored.bitrix_send_allowed)
        self.assertEqual(
            restored.observed_modes,
            (
                ConnectorMode.ACTIVE,
                ConnectorMode.REVIEW,
                ConnectorMode.SHADOW,
                ConnectorMode.ACTIVE,
            ),
        )

    def test_off_pauses_without_permanently_changing_active_capabilities(self):
        active = WorkflowGuard.from_mode(ConnectorMode.ACTIVE)
        paused = active.observe(ConnectorMode.OFF)

        self.assertFalse(paused.requires_input_approval)
        self.assertFalse(paused.requires_output_approval)
        self.assertTrue(paused.bitrix_send_allowed)
        self.assertEqual(paused.last_observed_mode, ConnectorMode.OFF)

    def test_actions_keep_blocked_content_in_review(self):
        active = WorkflowGuard.from_mode(ConnectorMode.ACTIVE)
        shadow = WorkflowGuard.from_mode(ConnectorMode.SHADOW)

        self.assertEqual(
            active.input_action(preflight_ready=False),
            WorkflowInputAction.NEEDS_REVIEW,
        )
        self.assertEqual(
            active.output_action(output_ready=False),
            WorkflowOutputAction.NEEDS_REVIEW,
        )
        self.assertEqual(
            shadow.output_action(output_ready=False),
            WorkflowOutputAction.SHADOW,
        )


if __name__ == "__main__":
    unittest.main()
