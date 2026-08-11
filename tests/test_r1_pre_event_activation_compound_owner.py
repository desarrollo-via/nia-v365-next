import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.r1_pre_event_activation_compound_owner import (
    CompoundProtectedParticipantOwner,
    CompoundProtectedParticipantProbePair,
    SanitizedProtectedParticipantSnapshot,
    build_compound_evidence_probes,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    BOT_NEXT_ID,
    BOT_NIA_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DEAL_ID,
    CONTROLLED_DIALOG_ID,
    PROTECTED_SETTING_COUNT,
    PROTECTED_TARGET_ID,
)


ROOT = Path(__file__).resolve().parents[1]


def exact_snapshot():
    return SanitizedProtectedParticipantSnapshot(
        host_supports_source=True,
        target_id=PROTECTED_TARGET_ID,
        record_shape_verified=True,
        setting_count=PROTECTED_SETTING_COUNT,
        credential_reads=1,
        oauth_reads=1,
        refresh_calls=0,
        retry_calls=0,
        review_auth_configured=True,
        deal_id=CONTROLLED_DEAL_ID,
        chat_id=CONTROLLED_CHAT_ID,
        dialog_id=CONTROLLED_DIALOG_ID,
        bot_nia_absent=True,
        bot_next_absent=True,
        participant_reads=1,
        participant_pages=1,
    )


class Session:
    def __init__(self, snapshot=None, error=None, close_error=None):
        self.snapshot = snapshot or exact_snapshot()
        self.error = error
        self.close_error = close_error
        self.events = []
        self.scopes = []

    async def collect_once(self, **scope):
        self.events.append("collect")
        self.scopes.append(scope)
        if self.error:
            raise self.error
        return self.snapshot

    async def close(self):
        self.events.append("close")
        if self.close_error:
            raise self.close_error


class Factory:
    def __init__(self, session):
        self.session = session
        self.builds = 0

    async def build(self):
        self.builds += 1
        return self.session


class R1CompoundOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_evidence_is_emitted_only_after_single_close(self):
        session = Session()
        owner = CompoundProtectedParticipantOwner(factory=Factory(session))

        result = await owner.collect_once()

        self.assertEqual(result.state, "EVIDENCE-COLLECTED")
        self.assertEqual(session.events, ["collect", "close"])
        self.assertEqual((result.session_builds, result.session_collects, result.session_closes), (1, 1, 1))
        self.assertTrue(result.resources_closed)
        self.assertFalse(result.activation_authorized)
        self.assertEqual(result.mutations, 0)

    async def test_session_receives_only_exact_frozen_scope(self):
        session = Session()
        await CompoundProtectedParticipantOwner(
            factory=Factory(session)
        ).collect_once()

        self.assertEqual(session.scopes, [{
            "target_id": PROTECTED_TARGET_ID,
            "expected_setting_count": PROTECTED_SETTING_COUNT,
            "deal_id": CONTROLLED_DEAL_ID,
            "chat_id": CONTROLLED_CHAT_ID,
            "dialog_id": CONTROLLED_DIALOG_ID,
            "bot_ids": (BOT_NIA_ID, BOT_NEXT_ID),
        }])

    async def test_any_budget_identity_or_secret_drift_is_no_go(self):
        changes = (
            {"credential_reads": 2},
            {"oauth_reads": 2},
            {"refresh_calls": 1},
            {"retry_calls": 1},
            {"chat_id": 1},
            {"bot_next_absent": False},
            {"participant_reads": 2},
            {"participant_pages": 2},
            {"secret_values_exposed": True},
        )
        for change in changes:
            with self.subTest(change=change):
                session = Session(snapshot=replace(exact_snapshot(), **change))
                result = await CompoundProtectedParticipantOwner(
                    factory=Factory(session)
                ).collect_once()
                self.assertEqual(result.state, "NO-GO")
                self.assertEqual(session.events, ["collect", "close"])

    async def test_private_exception_is_redacted_and_session_closes(self):
        private_text = "private-token-detail"
        session = Session(error=RuntimeError(private_text))

        result = await CompoundProtectedParticipantOwner(
            factory=Factory(session)
        ).collect_once()

        self.assertEqual(result.reason, "compound_evidence_invalid")
        self.assertNotIn(private_text, repr(result))
        self.assertEqual(session.events, ["collect", "close"])

    async def test_close_failure_is_terminal_and_emits_no_evidence(self):
        session = Session(close_error=RuntimeError("private-close-detail"))

        result = await CompoundProtectedParticipantOwner(
            factory=Factory(session)
        ).collect_once()

        self.assertEqual(result.reason, "resource_close_failed")
        self.assertIsNone(result.protected)
        self.assertIsNone(result.participants)
        self.assertFalse(result.resources_closed)

    async def test_owner_is_one_shot_without_second_session(self):
        factory = Factory(Session())
        owner = CompoundProtectedParticipantOwner(factory=factory)
        await owner.collect_once()

        repeated = await owner.collect_once()

        self.assertEqual(repeated.reason, "owner_reused")
        self.assertEqual(factory.builds, 1)

    async def test_probe_pair_caches_only_sanitized_participants(self):
        session = Session()
        protected_probe, participant_probe = build_compound_evidence_probes(
            owner=CompoundProtectedParticipantOwner(factory=Factory(session))
        )

        protected = await protected_probe.collect(
            target_id=PROTECTED_TARGET_ID,
            expected_setting_count=PROTECTED_SETTING_COUNT,
        )
        participants = await participant_probe.collect(
            deal_id=CONTROLLED_DEAL_ID,
            chat_id=CONTROLLED_CHAT_ID,
            dialog_id=CONTROLLED_DIALOG_ID,
            bot_ids=(BOT_NIA_ID, BOT_NEXT_ID),
        )

        self.assertTrue(protected.resources_closed)
        self.assertTrue(participants.bot_nia_absent)
        self.assertTrue(participants.bot_next_absent)
        self.assertEqual(session.events, ["collect", "close"])

    def test_module_has_no_real_source_network_or_private_output(self):
        text = (
            ROOT
            / "bitrix_connector"
            / "r1_pre_event_activation_compound_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "dotenv",
            "ctypes.",
            "credread",
            "secretclient",
            "get_secret",
            "get_access_token",
            "httpx",
            "requests",
            "subprocess",
            "print(",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
