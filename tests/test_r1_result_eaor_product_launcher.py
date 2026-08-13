import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from bitrix_connector.r1_result_eaor_product_launcher import (
    INERT_PREFLIGHT_CONFIRMATION,
    R1ResultEaorProductLauncher,
    drifted_bindings_for_test,
)
from scripts.run_r1_result_eaor_product_preflight import main


class R1ResultEaorProductLauncherTests(unittest.TestCase):
    def test_exact_preflight_is_ready_and_performs_zero_effects(self):
        result = R1ResultEaorProductLauncher(
            current_day="2026-08-13"
        ).preflight_once(
            confirmation=INERT_PREFLIGHT_CONFIRMATION
        )
        self.assertEqual(result.state, "READY-EXTERNAL-PREFLIGHT")
        self.assertTrue(result.exact_bindings_verified)
        self.assertTrue(result.exact_scope_verified)
        self.assertTrue(result.exact_literals_verified)
        self.assertTrue(result.exact_budgets_verified)
        self.assertEqual(result.coordinator_constructions, 0)
        self.assertEqual(result.owner_constructions, 0)
        self.assertEqual(result.external_calls, 0)
        self.assertEqual(result.protected_source_opens, 0)
        self.assertEqual(result.secret_reads, 0)
        self.assertEqual(result.mutations, 0)
        self.assertEqual(result.messages_sent, 0)
        self.assertTrue(result.execution_exposed)

    def test_next_day_requires_contract_refresh_before_external_preflight(self):
        result = R1ResultEaorProductLauncher(
            current_day="2026-08-14"
        ).preflight_once(confirmation=INERT_PREFLIGHT_CONFIRMATION)
        self.assertEqual(result.state, "READY-CONTRACT-REFRESH")
        self.assertFalse(result.external_envelope_current)
        self.assertTrue(result.exact_bindings_verified)
        self.assertEqual(result.external_calls, 0)

    def test_wrong_confirmation_stops_before_binding_audit(self):
        result = R1ResultEaorProductLauncher().preflight_once(
            confirmation="wrong"
        )
        self.assertEqual(result.state, "NO-GO-CONFIRMATION")
        self.assertFalse(result.exact_bindings_verified)

    def test_binding_identity_drift_fails_closed(self):
        result = R1ResultEaorProductLauncher(
            bindings=drifted_bindings_for_test(
                coordinator_builder=lambda **kwargs: None
            )
        ).preflight_once(confirmation=INERT_PREFLIGHT_CONFIRMATION)
        self.assertEqual(result.state, "NO-GO-BINDING-DRIFT")
        self.assertFalse(result.exact_bindings_verified)
        self.assertEqual(result.owner_constructions, 0)

    def test_preflight_is_one_shot_and_repr_is_redacted(self):
        launcher = R1ResultEaorProductLauncher(current_day="2026-08-13")
        self.assertEqual(
            repr(launcher), "R1ResultEaorProductLauncher(<redacted>)"
        )
        launcher.preflight_once(confirmation=INERT_PREFLIGHT_CONFIRMATION)
        with self.assertRaisesRegex(RuntimeError, "preflight_reused"):
            launcher.preflight_once(confirmation=INERT_PREFLIGHT_CONFIRMATION)

    def test_cli_emits_only_sanitized_preflight(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                ["--confirm-code", INERT_PREFLIGHT_CONFIRMATION],
                launcher_factory=lambda: R1ResultEaorProductLauncher(
                    current_day="2026-08-13"
                ),
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "READY-EXTERNAL-PREFLIGHT")
        self.assertEqual(payload["external_calls"], 0)
        self.assertTrue(payload["execution_exposed"])


if __name__ == "__main__":
    unittest.main()
