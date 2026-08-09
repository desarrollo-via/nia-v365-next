import unittest

from bitrix_connector.bitrix_event_scoped_r1_pre_event_oauth_adapter import (
    DormantStoredOAuthPreEventLeaseFactory,
)
from bitrix_connector.controlled_chat_participant_adapter import (
    ChatParticipantSnapshot,
    ParticipantSafetyState,
)
from bitrix_connector.controlled_chat_participant_http import (
    ParticipantHttpDecision,
    ParticipantMutationResult,
    ParticipantReadResult,
)


def safety():
    return ParticipantSafetyState(
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        runtime_state="inert",
        r0_mounted=False,
        r1_active=True,
    )


class Provider:
    def __init__(self):
        self.get_calls = 0
        self.refresh_calls = 0

    async def get_access_token(self, member_id):
        self.get_calls += 1
        return "fixture-private-token"

    async def refresh_access_token(self, *_args):
        self.refresh_calls += 1
        raise AssertionError("refresh must remain unreachable")


class OAuthResources:
    portal_url = "https://portal.bitrix24.test"
    member_id = "member-controlled"

    def __init__(self):
        self.oauth_provider = Provider()
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class Reader:
    def __init__(self, participants):
        self.participants = participants

    async def read(self):
        return ParticipantReadResult(
            decision=ParticipantHttpDecision.SUCCESS,
            snapshot=ChatParticipantSnapshot(
                crm_entity_id=614949,
                chat_id=78733,
                dialog_id="chat78733",
                participant_ids=frozenset(self.participants),
            ),
            pages=1,
        )


class Mutator:
    def __init__(self, participants):
        self.participants = participants

    async def mutate(self, contract):
        if contract.method.endswith(".add"):
            self.participants.add(373259)
        else:
            self.participants.discard(373259)
        return ParticipantMutationResult(
            decision=ParticipantHttpDecision.SUCCESS
        )


class HttpResources:
    def __init__(self, participants):
        self.reader = Reader(participants)
        self.mutator = Mutator(participants)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class InvalidResources:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class DormantStoredOAuthPreEventLeaseFactoryTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_is_dormant_until_arm_and_restores_on_disarm(self):
        resources = OAuthResources()
        participants = {27}
        http = HttpResources(participants)
        builder_calls = []

        async def builder():
            builder_calls.append(1)
            return resources

        factory = DormantStoredOAuthPreEventLeaseFactory(
            safety=safety(),
            resources_builder=builder,
            timeout_seconds=5.0,
            clock=lambda: 1000.0,
            http_resources_factory=lambda **_kwargs: http,
        )

        lease = factory()
        self.assertEqual(builder_calls, [])
        self.assertEqual(resources.oauth_provider.get_calls, 0)

        armed = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        restored = await lease.disarm_once()

        self.assertEqual(armed.state, "ARMED")
        self.assertEqual(restored.state, "DISARMED-RESTORED")
        self.assertEqual(builder_calls, [1])
        self.assertEqual(resources.oauth_provider.get_calls, 1)
        self.assertEqual(resources.oauth_provider.refresh_calls, 0)
        self.assertEqual(resources.close_calls, 1)
        self.assertEqual(http.close_calls, 1)
        self.assertEqual(participants, {27})
        self.assertNotIn("fixture-private-token", repr(factory))

    async def test_invalid_resources_are_closed_and_fail_terminally(self):
        resources = InvalidResources()

        async def builder():
            return resources

        lease = DormantStoredOAuthPreEventLeaseFactory(
            safety=safety(),
            resources_builder=builder,
            timeout_seconds=5.0,
            clock=lambda: 1000.0,
        )()

        result = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(result.state, "ROLLBACK-FAILED")
        self.assertEqual(resources.close_calls, 1)

    async def test_builder_failure_is_one_shot_and_never_retried(self):
        calls = []

        async def builder():
            calls.append(1)
            raise RuntimeError("private failure")

        factory = DormantStoredOAuthPreEventLeaseFactory(
            safety=safety(),
            resources_builder=builder,
            timeout_seconds=5.0,
            clock=lambda: 1000.0,
        )
        lease = factory()
        with self.assertRaisesRegex(RuntimeError, "factory_reused"):
            factory()

        first = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )
        second = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(first.state, "ROLLBACK-FAILED")
        self.assertEqual(second.state, "NO-GO")
        self.assertEqual(calls, [1])

    def test_source_has_no_real_binding_or_execution_surface(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "bitrix_connector"
            / "bitrix_event_scoped_r1_pre_event_oauth_adapter.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "pilotdiscoveryoauthfactory",
            "os.environ",
            "dotenv",
            "asyncio.run",
            "argparse",
            "subprocess",
            "print(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
