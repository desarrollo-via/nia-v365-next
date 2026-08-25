import unittest
from bitrix_connector.r1_result_eaor_coordinator import R1ResultEaorSnapshot
from scripts.run_r1_v3_two_phase_entrypoint import RESUME_CONFIRMATION, _sanitized, run_persistent_once

class Receipt:
    state = "ATTENTION-REQUIRED"; human_message_required_now = True; pre_event_lease_state = "AWAITING-EVENT"
class Controller:
    def __init__(self): self.calls = []
    async def start_until_human_once(self): self.calls.append("start"); return Receipt()
    async def resume_after_human_once(self): self.calls.append("resume"); return R1ResultEaorSnapshot(state="VERIFIED-RESTORED", resources_closed=True)
    async def close_waiting_once(self): self.calls.append("close"); return R1ResultEaorSnapshot(state="FAILED-RESTORED", resources_closed=True)
async def immediate(value): return value

class R1V3EntrypointTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_requires_explicit_human_decision_in_same_process(self):
        controller = Controller()
        result = await run_persistent_once(controller=controller, human_decision=lambda: immediate(RESUME_CONFIRMATION))
        self.assertEqual(result.state, "VERIFIED-RESTORED"); self.assertEqual(controller.calls, ["start", "resume"])
    async def test_any_other_decision_closes_waiting_session(self):
        controller = Controller()
        result = await run_persistent_once(controller=controller, human_decision=lambda: immediate("wrong"))
        self.assertEqual(result.state, "FAILED-RESTORED"); self.assertEqual(controller.calls, ["start", "close"])
    async def test_decision_failure_also_closes_waiting_session(self):
        controller = Controller()
        async def failure(): raise RuntimeError("console-lost")
        result = await run_persistent_once(controller=controller, human_decision=failure)
        self.assertEqual(result.state, "FAILED-RESTORED"); self.assertEqual(controller.calls, ["start", "close"])
    async def test_sanitizer_has_no_private_fields(self):
        payload = _sanitized(R1ResultEaorSnapshot(state="VERIFIED-RESTORED"))
        self.assertNotIn("token", str(payload).lower()); self.assertNotIn("secret", str(payload).lower())

if __name__ == "__main__": unittest.main()
