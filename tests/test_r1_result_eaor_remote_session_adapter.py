import unittest

from bitrix_connector.bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from bitrix_connector.bitrix_event_scoped_r1_gate import (
    EVENT_R1_FIRST_CONFIRMATION,
    EVENT_R1_SECOND_CONFIRMATION,
)
from bitrix_connector.r1_result_eaor_remote_session_adapter import (
    R1EaorRemoteSessionAdapter,
)


def snapshot(state, **changes):
    values = dict(state=state, consumed=False)
    values.update(changes)
    return EventR1ControlSnapshot(**values)


class Client:
    def __init__(self, statuses=None, *, disarm_ok=True):
        self.calls = []
        self.statuses = list(statuses or [])
        self.disarm_ok = disarm_ok

    async def first_confirmation_once(self, value):
        self.calls.append(("first", value))
        return snapshot("AWAITING-SECOND-CONFIRMATION")

    async def second_confirmation_once(self, value):
        self.calls.append(("second", value))
        return snapshot(
            "ATTENTION-REQUIRED", attention_required_now=True,
            human_message_required_now=True, pre_event_lease_bound=True,
            pre_event_lease_state="AWAITING-EVENT", participant_arm_attempts=1,
            human_message_authorizations=1,
        )

    async def status_once(self):
        self.calls.append(("status",))
        return self.statuses.pop(0)

    async def disarm_once(self):
        self.calls.append(("disarm",))
        return snapshot(
            "DISARMED", consumed=True, pre_event_lease_bound=True,
            pre_event_lease_state="RESTORED" if self.disarm_ok else "AWAITING-EVENT",
            participant_arm_attempts=1, participant_rollback_attempts=1,
            participant_rollback_verified=self.disarm_ok,
        )

    async def close(self):
        self.calls.append(("close",))


class R1EaorRemoteSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_arm_and_verified_remote_observation(self):
        client = Client([snapshot(
            "VERIFIED", consumed=True, pre_event_lease_bound=True,
            pre_event_lease_state="RESTORED", participant_arm_attempts=1,
            participant_rollback_attempts=1, participant_rollback_verified=True,
            human_message_authorizations=1,
        )])
        adapter = R1EaorRemoteSessionAdapter(client=client)
        self.assertEqual((await adapter.arm_once()).state, "ATTENTION-REQUIRED")
        result = await adapter.observe_after_human_once()
        self.assertEqual(result.state, "VERIFIED-RESTORED")
        self.assertEqual(client.calls, [
            ("first", EVENT_R1_FIRST_CONFIRMATION),
            ("second", EVENT_R1_SECOND_CONFIRMATION),
            ("status",), ("close",),
        ])

    async def test_close_while_waiting_disarms_before_closing(self):
        client = Client()
        adapter = R1EaorRemoteSessionAdapter(client=client)
        await adapter.arm_once()
        await adapter.close()
        self.assertEqual([item[0] for item in client.calls][-2:], ["disarm", "close"])

    async def test_timeout_disarms_and_reports_restored(self):
        now = [0.0]

        async def advance(_seconds):
            now[0] = 60.0

        client = Client([snapshot(
            "ATTENTION-REQUIRED", attention_required_now=True,
            human_message_required_now=True, pre_event_lease_bound=True,
            pre_event_lease_state="AWAITING-EVENT", participant_arm_attempts=1,
            human_message_authorizations=1,
        ), snapshot("ATTENTION-REQUIRED")])
        adapter = R1EaorRemoteSessionAdapter(
            client=client, observation_timeout_seconds=60,
            clock=lambda: now[0], sleeper=advance,
        )
        await adapter.arm_once()
        result = await adapter.observe_after_human_once()
        self.assertEqual(result.state, "EXPIRED-RESTORED")
        self.assertEqual([item[0] for item in client.calls][-2:], ["disarm", "close"])

    async def test_failed_timeout_rollback_is_visible(self):
        now = [0.0]

        async def advance(_seconds):
            now[0] = 60.0

        client = Client([
            snapshot("ATTENTION-REQUIRED"), snapshot("ATTENTION-REQUIRED")
        ], disarm_ok=False)
        adapter = R1EaorRemoteSessionAdapter(
            client=client, observation_timeout_seconds=60,
            clock=lambda: now[0], sleeper=advance,
        )
        await adapter.arm_once()
        result = await adapter.observe_after_human_once()
        self.assertEqual(result.state, "NO-GO-REMAINDER")
        self.assertFalse(result.resources_closed)

    async def test_terminal_failure_attempts_one_remote_recovery(self):
        client = Client([snapshot("NO-GO")])
        adapter = R1EaorRemoteSessionAdapter(client=client)
        await adapter.arm_once()
        result = await adapter.observe_after_human_once()
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertTrue(result.resources_closed)
        self.assertEqual([item[0] for item in client.calls][-2:], ["disarm", "close"])


if __name__ == "__main__":
    unittest.main()
