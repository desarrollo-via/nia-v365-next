import unittest

from bitrix_connector.bitrix_event_scoped_r1_participant_mount import (
    EventR1ParticipantMountFailure,
    EventR1ParticipantMountedRoundtrip,
)
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings
from bitrix_connector.controlled_chat_participant_adapter import (
    ChatParticipantSnapshot,
)
from bitrix_connector.controlled_chat_participant_http import (
    ParticipantHttpDecision,
    ParticipantMutationResult,
    ParticipantReadResult,
)
from bitrix_connector.models import NormalizedBitrixEvent


def settings():
    return load_settings(
        {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_EVENT_R1_ENABLED": "true",
            "NIA_BASE_URL": "https://nia.test",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-controlled",
            "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
            "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-1234567890",
            "NIA_BITRIX_REVIEW_ACTOR": "reviewer",
            "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "credential-fixture",
        }
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


def outcome():
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.READY,
            reason="bitrix_history_preflight_ready",
            dialog_read_calls=1,
            history_read_calls=0,
            dialog_verified=True,
            session_verified=True,
            baseline_captured=True,
            resources_closed=True,
        ),
        BitrixHistoryR0Anchor(700, 9001),
    )


class Result:
    state = "VERIFIED"


class MemoryReader:
    def __init__(self, state, order):
        self.state = state
        self.order = order

    async def read(self):
        self.order.append("read")
        return ParticipantReadResult(
            decision=ParticipantHttpDecision.SUCCESS,
            snapshot=ChatParticipantSnapshot(
                crm_entity_id=614949,
                chat_id=78733,
                dialog_id="chat78733",
                participant_ids=frozenset(self.state),
            ),
            pages=1,
        )

    async def close(self):
        self.order.append("reader_close")


class MemoryMutator:
    def __init__(self, state, order, *, reject_delete=False):
        self.state = state
        self.order = order
        self.reject_delete = reject_delete

    async def mutate(self, contract):
        if contract.method.endswith("user.add"):
            self.order.append("add")
            self.state.add(373259)
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.SUCCESS
            )
        self.order.append("delete")
        if self.reject_delete:
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.FAIL,
                error_code="fixture_delete_rejected",
            )
        self.state.discard(373259)
        return ParticipantMutationResult(
            decision=ParticipantHttpDecision.SUCCESS
        )

    async def close(self):
        self.order.append("mutator_close")


class MemoryResources:
    def __init__(self, state, order, *, reject_delete=False):
        self.reader = MemoryReader(state, order)
        self.mutator = MemoryMutator(
            state, order, reject_delete=reject_delete
        )
        self.order = order

    async def close(self):
        await self.mutator.close()
        await self.reader.close()
        self.order.append("resources_close")


class EventR1ParticipantMountedRoundtripTests(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip_runs_only_while_bot_next_is_linked_then_restores(self):
        state = {99}
        order = []
        resources = MemoryResources(state, order)

        def factory(**kwargs):
            self.assertEqual(kwargs["portal_url"], "https://portal.bitrix24.test")
            self.assertEqual(kwargs["access_token"], "event-token")
            return resources

        async def roundtrip(_settings, view, _outcome, _event):
            self.assertIn(373259, state)
            self.assertEqual(view.read_text(), "event-token")
            order.append("roundtrip")
            return Result()

        wrapper = EventR1ParticipantMountedRoundtrip(
            roundtrip=roundtrip,
            http_resources_factory=factory,
        )
        token = bytearray(b"event-token")
        view = StoredOAuthAccessView(token)
        result = await wrapper(settings(), view, outcome(), event())
        view.close()
        token[:] = b"\x00" * len(token)

        self.assertEqual(result.state, "VERIFIED")
        self.assertEqual(state, {99})
        self.assertEqual(
            order[:6],
            ["read", "add", "read", "roundtrip", "delete", "read"],
        )
        self.assertEqual(
            order[-3:],
            ["mutator_close", "reader_close", "resources_close"],
        )
        self.assertFalse(any(token))

    async def test_roundtrip_failure_still_restores_and_returns_no_go(self):
        state = {99}
        order = []
        resources = MemoryResources(state, order)

        async def roundtrip(*_args):
            order.append("roundtrip")
            raise RuntimeError("fixture roundtrip failure")

        wrapper = EventR1ParticipantMountedRoundtrip(
            roundtrip=roundtrip,
            http_resources_factory=lambda **_kwargs: resources,
        )
        token = bytearray(b"event-token")
        view = StoredOAuthAccessView(token)
        result = await wrapper(settings(), view, outcome(), event())
        view.close()
        token[:] = b"\x00" * len(token)

        self.assertIsInstance(result, EventR1ParticipantMountFailure)
        self.assertEqual(result.state, "NO-GO")
        self.assertTrue(result.rollback_verified)
        self.assertEqual(state, {99})
        self.assertLess(order.index("roundtrip"), order.index("delete"))

    async def test_unverified_participant_rollback_overrides_verified_roundtrip(self):
        state = {99}
        order = []
        resources = MemoryResources(state, order, reject_delete=True)

        async def roundtrip(*_args):
            order.append("roundtrip")
            return Result()

        wrapper = EventR1ParticipantMountedRoundtrip(
            roundtrip=roundtrip,
            http_resources_factory=lambda **_kwargs: resources,
        )
        token = bytearray(b"event-token")
        view = StoredOAuthAccessView(token)
        result = await wrapper(settings(), view, outcome(), event())
        view.close()
        token[:] = b"\x00" * len(token)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.participant_status, "rollback_failed")
        self.assertFalse(result.rollback_verified)
        self.assertIn(373259, state)

    async def test_wrapper_is_one_shot(self):
        state = {99}
        resources = MemoryResources(state, [])

        async def roundtrip(*_args):
            return Result()

        wrapper = EventR1ParticipantMountedRoundtrip(
            roundtrip=roundtrip,
            http_resources_factory=lambda **_kwargs: resources,
        )
        token = bytearray(b"event-token")
        view = StoredOAuthAccessView(token)
        await wrapper(settings(), view, outcome(), event())
        repeated = await wrapper(settings(), view, outcome(), event())
        view.close()
        token[:] = b"\x00" * len(token)

        self.assertEqual(repeated.state, "NO-GO")
        self.assertEqual(
            repeated.reason, "event_r1_participant_mount_already_used"
        )


if __name__ == "__main__":
    unittest.main()
