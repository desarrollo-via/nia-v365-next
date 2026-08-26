import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bitrix_connector.r1_post_write_close_real_binding import (
    R1PostWriteCloseDormantRealBinding,
)
from bitrix_connector.r1_post_write_close_recovery import R1PostWriteCloseRecovery


def write_valid_ledger(path: Path) -> None:
    path.write_text(json.dumps({
        "write_budget": 1,
        "write_reserved": 0,
        "write_succeeded": 1,
        "write_used": 1,
    }), encoding="utf-8")


class Surface:
    async def status_once(self): raise AssertionError("must remain dormant")
    async def disarm_once(self): raise AssertionError("must remain dormant")
    async def restore_exact_switches_once(self, plan):
        raise AssertionError("must remain dormant")
    async def restart_after_restore_once(self):
        raise AssertionError("must remain dormant")
    async def verify_dormant_once(self): raise AssertionError("must remain dormant")
    async def verify_closed_once(self): raise AssertionError("must remain dormant")
    async def close(self): raise AssertionError("must remain dormant")


class PostWriteCloseRealBindingTests(unittest.TestCase):
    def test_construction_and_preview_invoke_no_builder_or_effect(self):
        calls = []
        builder = lambda name: lambda: calls.append(name) or Surface()
        binding = R1PostWriteCloseDormantRealBinding(
            ledger_path=Path("unused-ledger.json"),
            session_client_builder=builder("session"),
            activation_control_builder=builder("activation"),
            key_vault_verifier_builder=builder("key_vault"),
        )
        preview = binding.preview()
        self.assertEqual(preview.state, "DORMANT")
        self.assertEqual(calls, [])
        self.assertEqual((preview.close_calls, preview.messages_sent,
                          preview.secret_write_calls, preview.resume_calls,
                          preview.external_calls), (0, 0, 0, 0, 0))

    def test_invalid_checkpoint_invokes_no_builder_and_is_terminal(self):
        calls = []
        builder = lambda: calls.append("called") or Surface()
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            ledger.write_text("{}", encoding="utf-8")
            binding = R1PostWriteCloseDormantRealBinding(
                ledger_path=ledger,
                session_client_builder=builder,
                activation_control_builder=builder,
                key_vault_verifier_builder=builder,
            )
            with self.assertRaisesRegex(RuntimeError, "checkpoint_invalid"):
                binding.build_recovery_once()
            self.assertEqual(calls, [])
            self.assertEqual(binding.preview().state, "NO-GO-CHECKPOINT")
            with self.assertRaisesRegex(RuntimeError, "binding_reused"):
                binding.build_recovery_once()

    def test_valid_checkpoint_builds_recovery_without_factories_or_effect(self):
        calls = []
        builder = lambda name: lambda: calls.append(name) or Surface()
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            write_valid_ledger(ledger)
            binding = R1PostWriteCloseDormantRealBinding(
                ledger_path=ledger,
                session_client_builder=builder("session"),
                activation_control_builder=builder("activation"),
                key_vault_verifier_builder=builder("key_vault"),
            )
            recovery = binding.build_recovery_once()
            self.assertIs(type(recovery), R1PostWriteCloseRecovery)
            self.assertEqual(calls, [])
            preview = binding.preview()
            self.assertEqual(preview.state, "BOUND-DORMANT")
            self.assertEqual(preview.builder_calls, 0)
            self.assertEqual((preview.close_calls, preview.messages_sent,
                              preview.secret_write_calls, preview.resume_calls,
                              preview.external_calls), (0, 0, 0, 0, 0))
            self.assertEqual(
                repr(binding),
                "R1PostWriteCloseDormantRealBinding(<redacted>)",
            )
            with self.assertRaisesRegex(RuntimeError, "binding_reused"):
                binding.build_recovery_once()


if __name__ == "__main__":
    unittest.main()
