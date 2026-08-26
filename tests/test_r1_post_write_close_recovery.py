import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bitrix_connector.r1_post_write_close_recovery import (
    PostWriteSurfaceCloseResult,
    R1PostWriteActivationCloser,
    R1PostWriteCloseRecovery,
    R1PostWriteKeyVaultCloser,
    R1PostWriteSessionCloser,
    verify_consumed_write_checkpoint,
)
from bitrix_connector.bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from bitrix_connector.r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES, SWITCH_ORDER,
)


def write_ledger(path: Path, **changes):
    payload = {
        "write_budget": 1, "write_reserved": 0,
        "write_succeeded": 1, "write_used": 1,
    }
    payload.update(changes)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PostWriteCloseRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_closes_in_safety_order_and_never_resumes_or_writes(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            write_ledger(ledger)
            calls = []

            def closure(name):
                async def run():
                    calls.append(name)
                    return PostWriteSurfaceCloseResult(
                        "VERIFIED-CLOSED", True, effect_calls=1
                    )
                return run

            recovery = R1PostWriteCloseRecovery(
                ledger_path=ledger,
                session_close=closure("session"),
                activation_close=closure("activation"),
                key_vault_close=closure("key_vault"),
            )
            result = await recovery.close_once()
            self.assertEqual(result.state, "VERIFIED-RESTORED")
            self.assertEqual(calls, ["session", "activation", "key_vault"])
            self.assertEqual(result.closure_attempts, 3)
            self.assertEqual(result.messages_sent, 0)
            self.assertEqual(result.secret_write_calls, 0)
            self.assertEqual(result.resume_calls, 0)
            self.assertTrue(result.resources_closed)
            self.assertEqual(repr(recovery), "R1PostWriteCloseRecovery(<redacted>)")

    async def test_invalid_checkpoint_constructs_no_closure(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            write_ledger(ledger, write_reserved=1)
            calls = []
            async def forbidden():
                calls.append("called")
                raise AssertionError("closure must remain dormant")
            result = await R1PostWriteCloseRecovery(
                ledger_path=ledger, session_close=forbidden,
                activation_close=forbidden, key_vault_close=forbidden,
            ).close_once()
            self.assertEqual(result.state, "NO-GO-CHECKPOINT")
            self.assertEqual(result.closure_attempts, 0)
            self.assertEqual(calls, [])

    async def test_failure_still_attempts_remaining_safety_closures(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            write_ledger(ledger)
            calls = []
            async def session():
                calls.append("session")
                return PostWriteSurfaceCloseResult("NO-GO-REMAINDER", True)
            async def activation():
                calls.append("activation")
                raise RuntimeError("fixture")
            async def key_vault():
                calls.append("key_vault")
                return PostWriteSurfaceCloseResult("VERIFIED-CLOSED", True)
            result = await R1PostWriteCloseRecovery(
                ledger_path=ledger, session_close=session,
                activation_close=activation, key_vault_close=key_vault,
            ).close_once()
            self.assertEqual(result.state, "NO-GO-REMAINDER")
            self.assertEqual(calls, ["session", "activation", "key_vault"])
            self.assertEqual(result.failure_surface, "session")
            self.assertFalse(result.resources_closed)

    async def test_recovery_is_one_shot(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            write_ledger(ledger)
            async def yes():
                return PostWriteSurfaceCloseResult("VERIFIED-CLOSED", True)
            recovery = R1PostWriteCloseRecovery(
                ledger_path=ledger, session_close=yes,
                activation_close=yes, key_vault_close=yes,
            )
            await recovery.close_once()
            with self.assertRaisesRegex(RuntimeError, "reused"):
                await recovery.close_once()

    def test_checkpoint_rejects_extra_fields_and_non_integer_values(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            write_ledger(ledger)
            self.assertTrue(verify_consumed_write_checkpoint(ledger))
            write_ledger(ledger, extra=1)
            self.assertFalse(verify_consumed_write_checkpoint(ledger))
            write_ledger(ledger, write_succeeded=True)
            self.assertFalse(verify_consumed_write_checkpoint(ledger))

    async def test_session_closer_never_sends_confirmation(self):
        class Client:
            def __init__(self): self.calls = []
            async def status_once(self):
                self.calls.append("status")
                return EventR1ControlSnapshot(
                    state="ATTENTION-REQUIRED", consumed=False,
                    pre_event_lease_bound=True,
                    pre_event_lease_state="AWAITING-EVENT",
                    participant_arm_attempts=1,
                    human_message_authorizations=1,
                )
            async def disarm_once(self):
                self.calls.append("disarm")
                return EventR1ControlSnapshot(
                    state="DISARMED", consumed=True,
                    pre_event_lease_bound=True,
                    pre_event_lease_state="RESTORED",
                    participant_arm_attempts=1,
                    participant_rollback_attempts=1,
                    participant_rollback_verified=True,
                )
            async def close(self): self.calls.append("close")
        client = Client()
        result = await R1PostWriteSessionCloser(client=client).close_once()
        self.assertEqual(result.state, "VERIFIED-CLOSED")
        self.assertEqual(client.calls, ["status", "disarm", "close"])

    async def test_session_closer_accepts_exact_never_armed_state(self):
        class Client:
            def __init__(self): self.calls = []
            async def status_once(self):
                self.calls.append("status")
                return EventR1ControlSnapshot(state="IDLE", consumed=False)
            async def disarm_once(self):
                raise AssertionError("must not disarm inert session")
            async def close(self): self.calls.append("close")
        client = Client()
        result = await R1PostWriteSessionCloser(client=client).close_once()
        self.assertEqual(result.state, "VERIFIED-CLOSED")
        self.assertEqual(client.calls, ["status", "close"])

    async def test_activation_closer_restores_known_baseline(self):
        class Control:
            def __init__(self): self.calls = []
            async def restore_exact_switches_once(self, plan):
                self.calls.append(("restore", plan))
            async def restart_after_restore_once(self):
                self.calls.append(("restart",))
            async def verify_dormant_once(self):
                self.calls.append(("verify",)); return True
            async def close(self): self.calls.append(("close",))
        control = Control()
        result = await R1PostWriteActivationCloser(control=control).close_once()
        expected = tuple(
            f"restore-value:{name}={EXPECTED_BASELINE_VALUES[name]}"
            for name in SWITCH_ORDER
        )
        self.assertEqual(result.state, "VERIFIED-CLOSED")
        self.assertEqual(control.calls, [
            ("restore", expected), ("restart",), ("verify",), ("close",)
        ])

    async def test_key_vault_closer_is_read_only_verification(self):
        class Verifier:
            def __init__(self): self.calls = []
            async def verify_closed_once(self):
                self.calls.append("verify"); return True
            async def close(self): self.calls.append("close")
        verifier = Verifier()
        result = await R1PostWriteKeyVaultCloser(
            verifier=verifier
        ).close_once()
        self.assertEqual(result.state, "VERIFIED-CLOSED")
        self.assertEqual(verifier.calls, ["verify", "close"])


if __name__ == "__main__":
    unittest.main()
