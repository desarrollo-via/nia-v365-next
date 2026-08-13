import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from bitrix_connector.r1_result_eaor_remote_preflight_real_binding import (
    CONSTRUCTION_AUDIT_CONFIRMATION,
    R1RemotePreflightDormantRealBinding,
)
from scripts.run_r1_remote_preflight_construction_audit import main


class R1RemotePreflightRealBindingTests(unittest.TestCase):
    def test_construction_and_coordinator_build_invoke_no_dependency(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("deferred dependency invoked")

        binding = R1RemotePreflightDormantRealBinding(
            local_state_guard=forbidden,
            diagnostic_builder=forbidden,
            runner_factory=forbidden,
            health_factory=forbidden,
        )
        self.assertEqual(binding.preview().state, "DORMANT")
        coordinator = binding.build_coordinator_once()
        preview = binding.preview()
        self.assertEqual(preview.state, "BOUND-DORMANT")
        self.assertEqual(preview.coordinator_constructions, 1)
        self.assertEqual(coordinator.preview().state, "INERT")
        self.assertEqual(calls, [])

    def test_preview_has_fixed_zero_effect_surface(self):
        binding = R1RemotePreflightDormantRealBinding(
            local_state_guard=lambda: True
        )
        binding.build_coordinator_once()
        preview = binding.preview()
        self.assertEqual(preview.diagnostic_constructions, 0)
        self.assertEqual(preview.runner_constructions, 0)
        self.assertEqual(preview.health_reader_constructions, 0)
        self.assertEqual(preview.local_state_guard_calls, 0)
        self.assertEqual(preview.run_calls, 0)
        self.assertEqual(preview.external_calls, 0)
        self.assertEqual(preview.secret_reads, 0)
        self.assertEqual(preview.mutations, 0)
        self.assertFalse(preview.execution_authorized)

    def test_binding_is_one_shot_and_redacted(self):
        binding = R1RemotePreflightDormantRealBinding(
            local_state_guard=lambda: True
        )
        self.assertEqual(
            repr(binding),
            "R1RemotePreflightDormantRealBinding(<redacted>)",
        )
        binding.build_coordinator_once()
        with self.assertRaisesRegex(RuntimeError, "binding_reused"):
            binding.build_coordinator_once()

    def test_invalid_dependency_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "dependency_invalid"):
            R1RemotePreflightDormantRealBinding(local_state_guard=None)

    def test_cli_outputs_only_construction_preview(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--confirm-code", CONSTRUCTION_AUDIT_CONFIRMATION,
            ])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "BOUND-DORMANT")
        self.assertEqual(payload["coordinator_state"], "INERT")
        self.assertEqual(payload["diagnostic_constructions"], 0)
        self.assertEqual(payload["external_calls"], 0)
        self.assertFalse(payload["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
