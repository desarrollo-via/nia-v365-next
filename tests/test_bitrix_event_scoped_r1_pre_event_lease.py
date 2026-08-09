import unittest

from bitrix_connector.bitrix_event_scoped_r1_pre_event_lease import (
    PreEventLeaseArmEvidence,
    PreEventLeaseRollbackEvidence,
    PreEventParticipantLease,
)
from bitrix_connector.config import load_settings
from bitrix_connector.controlled_chat_participant_adapter import (
    ParticipantSafetyState,
)
from bitrix_connector.models import NormalizedBitrixEvent


FINGERPRINT = "a" * 64


def safety(**changes):
    values = {
        "effective_mode": "off",
        "activation_locked": True,
        "external_calls_enabled": False,
        "runtime_state": "inert",
        "r0_mounted": False,
        "r1_active": True,
    }
    values.update(changes)
    return ParticipantSafetyState(**values)


def event(**changes):
    values = {
        "event": "ONIMBOTV2MESSAGEADD",
        "bot_id": 373259,
        "message_id": 9001,
        "chat_id": 78733,
        "dialog_id": "chat78733",
        "author_id": 27,
        "text": "fixture",
        "user_id": 27,
        "user_is_connector": True,
        "domain": "portal.bitrix24.test",
        "member_id": "member-controlled",
    }
    values.update(changes)
    return NormalizedBitrixEvent.model_validate(values)


class Operations:
    def __init__(self, *, linked=True, restored=True):
        self.linked = linked
        self.restored = restored
        self.arm_calls = 0
        self.rollback_calls = 0
        self.rollback_fingerprint = None

    async def arm(self):
        self.arm_calls += 1
        return PreEventLeaseArmEvidence(
            exact_scope=True,
            linked_verified=self.linked,
            bot_nia_absent=True,
            baseline_fingerprint=FINGERPRINT,
        )

    async def rollback(self, baseline_fingerprint):
        self.rollback_calls += 1
        self.rollback_fingerprint = baseline_fingerprint
        return PreEventLeaseRollbackEvidence(
            exact_scope=True,
            restored_verified=self.restored,
            bot_next_absent=True,
            bot_nia_absent=True,
            restored_fingerprint=FINGERPRINT,
        )


class PreEventParticipantLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_arms_after_confirmation_and_allows_one_human_message(self):
        now = [1000.0]
        operations = Operations()
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: now[0],
        )

        armed = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(armed.state, "ARMED")
        self.assertTrue(armed.lease_verified)
        self.assertTrue(armed.deadline_bound)
        self.assertTrue(armed.human_message_allowed_now)
        self.assertTrue(armed.baseline_fingerprint_retained)
        self.assertEqual(operations.arm_calls, 1)

        authorized = await lease.consume_human_message_authorization_once()
        self.assertEqual(authorized.state, "AWAITING-EVENT")
        self.assertEqual(authorized.human_message_authorizations, 1)
        self.assertFalse(authorized.human_message_allowed_now)

    async def test_exact_event_claim_then_release_restores_once(self):
        operations = Operations()
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: 1000.0,
        )
        await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        await lease.consume_human_message_authorization_once()

        claimed = await lease.claim_exact_event_once(event())
        restored = await lease.release_after_event_once()
        repeated = await lease.release_after_event_once()

        self.assertEqual(claimed.state, "EVENT-CLAIMED")
        self.assertFalse(claimed.human_message_allowed_now)
        self.assertEqual(restored.state, "RESTORED")
        self.assertTrue(restored.rollback_verified)
        self.assertFalse(restored.baseline_fingerprint_retained)
        self.assertEqual(repeated.state, "RESTORED")
        self.assertEqual(operations.rollback_calls, 1)
        self.assertEqual(operations.rollback_fingerprint, FINGERPRINT)

    async def test_wrong_event_does_not_consume_or_release_lease(self):
        operations = Operations()
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: 1000.0,
        )
        await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        await lease.consume_human_message_authorization_once()

        ignored = await lease.claim_exact_event_once(event(chat_id=1))

        self.assertEqual(ignored.state, "AWAITING-EVENT")
        self.assertEqual(ignored.event_claims, 0)
        self.assertEqual(operations.rollback_calls, 0)

    async def test_ttl_expiry_rolls_back_and_never_allows_message_again(self):
        now = [1000.0]
        operations = Operations()
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: now[0],
        )
        await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        now[0] = 1060.0

        expired = await lease.expire_if_due()

        self.assertEqual(expired.state, "EXPIRED-RESTORED")
        self.assertTrue(expired.rollback_verified)
        self.assertFalse(expired.human_message_allowed_now)
        self.assertEqual(operations.rollback_calls, 1)

    async def test_second_human_message_authorization_rolls_back(self):
        operations = Operations()
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: 1000.0,
        )
        await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        await lease.consume_human_message_authorization_once()

        repeated = await lease.consume_human_message_authorization_once()

        self.assertEqual(repeated.state, "FAILED-RESTORED")
        self.assertTrue(repeated.rollback_verified)
        self.assertEqual(repeated.human_message_authorizations, 1)
        self.assertEqual(operations.rollback_calls, 1)

    async def test_disarm_and_close_each_restore_an_active_lease(self):
        for action, expected in (
            ("disarm_once", "DISARMED-RESTORED"),
            ("close", "CLOSED-RESTORED"),
        ):
            with self.subTest(action=action):
                operations = Operations()
                lease = PreEventParticipantLease(
                    safety=safety(),
                    arm=operations.arm,
                    rollback=operations.rollback,
                    clock=lambda: 1000.0,
                )
                await lease.arm_after_second_confirmation_once(
                    session_deadline=1060.0
                )

                result = await getattr(lease, action)()

                self.assertEqual(result.state, expected)
                self.assertTrue(result.rollback_verified)
                self.assertEqual(operations.rollback_calls, 1)

    async def test_failed_arm_still_runs_one_exact_rollback(self):
        operations = Operations(linked=False)
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: 1000.0,
        )

        result = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertTrue(result.rollback_verified)
        self.assertEqual((operations.arm_calls, operations.rollback_calls), (1, 1))

    async def test_rollback_mismatch_is_terminal_and_visible(self):
        operations = Operations(restored=False)
        lease = PreEventParticipantLease(
            safety=safety(),
            arm=operations.arm,
            rollback=operations.rollback,
            clock=lambda: 1000.0,
        )
        await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        await lease.consume_human_message_authorization_once()
        await lease.claim_exact_event_once(event())

        result = await lease.release_after_event_once()

        self.assertEqual(result.state, "ROLLBACK-FAILED")
        self.assertFalse(result.rollback_verified)
        self.assertEqual(operations.rollback_calls, 1)

    async def test_unsafe_or_expired_preflight_blocks_before_arm(self):
        cases = (
            (safety(r0_mounted=True), 1060.0),
            (safety(), 999.0),
            (safety(), 1601.0),
        )
        for safety_state, deadline in cases:
            with self.subTest(deadline=deadline):
                operations = Operations()
                lease = PreEventParticipantLease(
                    safety=safety_state,
                    arm=operations.arm,
                    rollback=operations.rollback,
                    clock=lambda: 1000.0,
                )

                result = await lease.arm_after_second_confirmation_once(
                    session_deadline=deadline
                )

                self.assertEqual(result.state, "NO-GO")
                self.assertEqual(operations.arm_calls, 0)
                self.assertEqual(operations.rollback_calls, 0)


if __name__ == "__main__":
    unittest.main()
