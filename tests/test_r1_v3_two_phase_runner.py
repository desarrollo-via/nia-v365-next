import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bitrix_connector.r1_result_eaor_coordinator import R1ResultEaorSnapshot
from bitrix_connector.r1_v3_two_phase_runner import R1V3SanitizedCheckpointStore, R1V3TwoPhaseRunner
from bitrix_connector.r1_v3_two_phase_runtime import build_dormant_r1_v3_two_phase_runner


class RunnerDouble:
    def __init__(self): self.calls = []
    async def run_until_human_once(self):
        self.calls.append("start")
        return R1ResultEaorSnapshot(state="ATTENTION-REQUIRED", acceptance_calls=1, provisioning_calls=1, activation_calls=1, session_arm_calls=1, human_message_required_now=True, pre_event_lease_state="AWAITING-EVENT")
    async def resume_after_human_once(self):
        self.calls.append("resume")
        return R1ResultEaorSnapshot(state="VERIFIED-RESTORED", resources_closed=True)
    async def close_waiting_once(self):
        self.calls.append("close")
        return R1ResultEaorSnapshot(state="FAILED-RESTORED", resources_closed=True)


class R1V3TwoPhaseRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_v3_composition_is_dormant(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            controller = build_dormant_r1_v3_two_phase_runner(checkpoint_path=root / "receipt.json", ledger_path=root / "write-ledger.json", expected_deployed_sha="a" * 40, expected_deployed_tree="b" * 40, local_state_guard=lambda: True, current_day="2026-08-25")
            self.assertIsInstance(controller, R1V3TwoPhaseRunner)
            self.assertFalse((root / "receipt.json").exists())
            self.assertFalse((root / "write-ledger.json").exists())

    async def test_receipt_is_sanitized_and_resume_is_separate(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            runner = RunnerDouble()
            controller = R1V3TwoPhaseRunner(runner=runner, checkpoint=R1V3SanitizedCheckpointStore(path=path))
            receipt = await controller.start_until_human_once()
            self.assertEqual(receipt.state, "ATTENTION-REQUIRED")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(payload), {"schema", "receipt", "snapshot_sha256"})
            self.assertNotIn("token", json.dumps(payload).lower())
            self.assertNotIn("secret", json.dumps(payload).lower())
            self.assertEqual((await controller.resume_after_human_once()).state, "VERIFIED-RESTORED")
            self.assertEqual(runner.calls, ["start", "resume"])

    async def test_fresh_process_and_tamper_block_resume(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            first = R1V3TwoPhaseRunner(runner=RunnerDouble(), checkpoint=R1V3SanitizedCheckpointStore(path=path))
            await first.start_until_human_once()
            fresh = R1V3TwoPhaseRunner(runner=RunnerDouble(), checkpoint=R1V3SanitizedCheckpointStore(path=path))
            with self.assertRaisesRegex(RuntimeError, "process_checkpoint_required"):
                await fresh.resume_after_human_once()
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["receipt"]["state"] = "VERIFIED-RESTORED"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "checkpoint_tampered"):
                await first.resume_after_human_once()


if __name__ == "__main__": unittest.main()
