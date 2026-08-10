import unittest

from bitrix_connector.bitrix_event_scoped_r1_pre_event_lease_factory import (
    InjectedPreEventParticipantLeaseFactory,
    participant_snapshot_fingerprint,
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
from bitrix_connector.models import NormalizedBitrixEvent


def safety():
    return ParticipantSafetyState(
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        runtime_state="inert",
        r0_mounted=False,
        r1_active=True,
    )


def snapshot(participants):
    return ChatParticipantSnapshot(
        crm_entity_id=614949,
        chat_id=78733,
        dialog_id="chat78733",
        participant_ids=frozenset(participants),
    )


def event():
    return NormalizedBitrixEvent.model_validate(
        {
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
    )


class Provider:
    def __init__(self, order):
        self.order = order
        self.calls = 0

    async def get_access_token(self, member_id):
        self.calls += 1
        self.order.append(("token", member_id))
        return "fixture-secret-token"


class OAuthResources:
    portal_url = "https://portal.bitrix24.test"
    member_id = "member-controlled"

    def __init__(self, order):
        self.order = order
        self.oauth_provider = Provider(order)
        self.closed = False

    async def close(self):
        self.closed = True
        self.order.append("oauth-close")


class Reader:
    def __init__(self, participants, order):
        self.participants = participants
        self.order = order

    async def read(self):
        self.order.append("read")
        return ParticipantReadResult(
            decision=ParticipantHttpDecision.SUCCESS,
            snapshot=snapshot(self.participants),
            pages=1,
        )


class Mutator:
    def __init__(self, participants, order, rejected_method=None):
        self.participants = participants
        self.order = order
        self.rejected_method = rejected_method

    async def mutate(self, contract):
        action = contract.method.rsplit(".", 1)[-1]
        self.order.append(action)
        if contract.method == self.rejected_method:
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.FAIL,
                error_code="fixture_rejected",
            )
        if action == "add":
            self.participants.add(373259)
        else:
            self.participants.discard(373259)
        return ParticipantMutationResult(
            decision=ParticipantHttpDecision.SUCCESS
        )


class HttpResources:
    def __init__(self, participants, order, rejected_method=None):
        self.reader = Reader(participants, order)
        self.mutator = Mutator(participants, order, rejected_method)
        self.order = order
        self.closed = False

    async def close(self):
        self.closed = True
        self.order.append("http-close")


class Harness:
    def __init__(self, participants=(27,), rejected_method=None):
        self.order = []
        self.participants = set(participants)
        self.oauth = OAuthResources(self.order)
        self.http = HttpResources(
            self.participants, self.order, rejected_method
        )
        self.build_kwargs = None

    def build_http(self, **kwargs):
        self.build_kwargs = kwargs
        return self.http

    def factory(self):
        return InjectedPreEventParticipantLeaseFactory(
            safety=safety(),
            oauth_resources_factory=lambda: self.oauth,
            timeout_seconds=5.0,
            clock=lambda: 1000.0,
            http_resources_factory=self.build_http,
        )


class InjectedPreEventParticipantLeaseFactoryTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_holds_resources_until_exact_event_rollback(self):
        harness = Harness()
        factory = harness.factory()
        lease = factory()

        armed = await lease.arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(armed.state, "ARMED")
        self.assertEqual(harness.participants, {27, 373259})
        self.assertFalse(harness.http.closed)
        self.assertFalse(harness.oauth.closed)
        self.assertEqual(harness.oauth.oauth_provider.calls, 1)
        self.assertNotIn("fixture-secret-token", repr(factory))
        self.assertEqual(harness.build_kwargs["access_token"], "fixture-secret-token")

        await lease.consume_human_message_authorization_once()
        await lease.claim_exact_event_once(event())
        restored = await lease.release_after_event_once()

        self.assertEqual(restored.state, "RESTORED")
        self.assertTrue(restored.rollback_verified)
        self.assertEqual(harness.participants, {27})
        self.assertEqual(
            harness.order,
            [
                ("token", "member-controlled"),
                "read",
                "add",
                "read",
                "delete",
                "read",
                "http-close",
                "oauth-close",
            ],
        )

    async def test_add_attempt_always_gets_one_rollback_attempt(self):
        harness = Harness(
            rejected_method="imopenlines.crm.chat.user.add"
        )
        result = await harness.factory()().arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(harness.order.count("add"), 1)
        self.assertEqual(harness.order.count("delete"), 1)
        self.assertEqual(harness.participants, {27})
        self.assertTrue(harness.http.closed)
        self.assertTrue(harness.oauth.closed)

    async def test_invalid_baseline_never_sends_preventive_delete(self):
        harness = Harness(participants=(27, 373259))
        result = await harness.factory()().arm_after_second_confirmation_once(
            session_deadline=1060.0
        )

        self.assertEqual(result.state, "ROLLBACK-FAILED")
        self.assertNotIn("add", harness.order)
        self.assertNotIn("delete", harness.order)
        self.assertTrue(harness.http.closed)
        self.assertTrue(harness.oauth.closed)

    async def test_failed_delete_is_visible_as_rollback_failed(self):
        harness = Harness(
            rejected_method="imopenlines.crm.chat.user.delete"
        )
        lease = harness.factory()()
        await lease.arm_after_second_confirmation_once(session_deadline=1060.0)
        await lease.consume_human_message_authorization_once()
        await lease.claim_exact_event_once(event())

        result = await lease.release_after_event_once()

        self.assertEqual(result.state, "ROLLBACK-FAILED")
        self.assertEqual(harness.participants, {27, 373259})
        self.assertTrue(harness.http.closed)
        self.assertTrue(harness.oauth.closed)

    async def test_ttl_expiry_restores_and_factory_is_one_shot(self):
        now = [1000.0]
        harness = Harness()
        factory = InjectedPreEventParticipantLeaseFactory(
            safety=safety(),
            oauth_resources_factory=lambda: harness.oauth,
            timeout_seconds=5.0,
            clock=lambda: now[0],
            http_resources_factory=harness.build_http,
        )
        lease = factory()
        with self.assertRaisesRegex(RuntimeError, "factory_reused"):
            factory()
        await lease.arm_after_second_confirmation_once(session_deadline=1060.0)
        now[0] = 1060.0

        result = await lease.expire_if_due()

        self.assertEqual(result.state, "EXPIRED-RESTORED")
        self.assertEqual(harness.participants, {27})

    def test_fingerprint_is_order_independent_and_scope_bound(self):
        first = participant_snapshot_fingerprint(snapshot((27, 99)))
        second = participant_snapshot_fingerprint(snapshot((99, 27)))
        changed = participant_snapshot_fingerprint(snapshot((27,)))

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertEqual(len(first), 64)


if __name__ == "__main__":
    unittest.main()
