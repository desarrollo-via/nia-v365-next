import unittest
from pathlib import Path

from bitrix_connector.modes import ConnectorMode
from bitrix_connector.review_lab import (
    build_simulated_review_lab_html,
    build_simulated_review_lab_view,
)


class ReviewLabTests(unittest.TestCase):
    def test_fixture_uses_shadow_scenario_while_real_state_stays_off(self):
        view = build_simulated_review_lab_view()

        self.assertTrue(view.simulation)
        self.assertEqual(view.status, "shadowed")
        self.assertEqual(view.safety.real_effective_mode, ConnectorMode.OFF)
        self.assertEqual(view.safety.scenario_mode, ConnectorMode.SHADOW)
        self.assertTrue(view.safety.activation_locked)
        self.assertFalse(view.safety.external_calls_enabled)
        self.assertFalse(view.safety.real_connections_used)
        self.assertFalse(view.workflow_guard.bitrix_send_allowed)
        self.assertIsNone(view.outbound_message_id)
        self.assertEqual(view.shadow_result["bitrix_attempt_count"], 0)

    def test_fixture_exposes_the_six_review_artifacts(self):
        view = build_simulated_review_lab_view()

        self.assertEqual(
            view.original_event_redacted["auth[application_token]"],
            "[REDACTED]",
        )
        self.assertEqual(
            view.normalized_message.text,
            "Necesito una bomba centrífuga para agua limpia, 10 HP.",
        )
        self.assertEqual(view.attachment_manifest.attachment_count, 0)
        self.assertEqual(
            view.nia_payload.mensaje,
            view.normalized_message.text,
        )
        self.assertEqual(view.nia_response.etapa, "descubrimiento")
        self.assertEqual(
            view.bitrix_payload_preview.dialogId,
            "chat-controlado-001",
        )

    def test_html_is_self_contained_read_only_and_contains_no_fixture_secret(self):
        html = build_simulated_review_lab_html()

        self.assertIn("SIMULACIÓN LOCAL · MODO REAL OFF", html)
        self.assertIn('data-simulation="true"', html)
        self.assertIn("chat-controlado-001", html)
        self.assertIn("[REDACTED]", html)
        self.assertIn("&quot;original_text_length&quot;: 58", html)
        self.assertIn("&quot;normalized_text_length&quot;: 54", html)
        self.assertNotIn("fixture-secret-never-display", html)
        self.assertEqual(html.count("<button disabled>"), 4)
        self.assertNotIn("<script", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_openable_demo_is_static_and_keeps_actions_disabled(self):
        demo_path = (
            Path(__file__).resolve().parents[1]
            / "bitrix_connector"
            / "review_lab_demo.html"
        )
        html = demo_path.read_text(encoding="utf-8")
        view = build_simulated_review_lab_view()

        self.assertIn("SIMULACIÓN LOCAL · MODO REAL OFF", html)
        self.assertIn("chat-controlado-001", html)
        self.assertIn("[REDACTED]", html)
        self.assertIn(view.event_key, html)
        self.assertIn(view.input_content_hash, html)
        self.assertIn(view.output_content_hash, html)
        self.assertNotIn("fixture-secret-never-display", html)
        self.assertEqual(html.count("<button disabled>"), 4)
        self.assertNotIn("<script", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main()
