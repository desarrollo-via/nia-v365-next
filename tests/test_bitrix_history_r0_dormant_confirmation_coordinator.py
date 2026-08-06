import asyncio
import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_dormant_confirmation_coordinator import (
    FIRST_CONFIRMATION_SCOPE,
    MANUAL_REMOVAL_SCOPE,
    SECOND_CONFIRMATION_SCOPE,
    DormantTwoConfirmationCoordinator,
    InjectedConfirmation,
    InjectedFreshPreflightEvidence,
    InjectedManualRemovalEvidence,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from bitrix_connector.bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
    ComposedRoundtripStatus,
)


ROOT = Path(__file__).resolve().parents[1]


class Probe:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


def verified_roundtrip():
    return ComposedRoundtripResult(
        status=ComposedRoundtripStatus.VERIFIED,
        reason="composed_roundtrip_verified_and_preserved",
        post_send_history_read_count=1,
        rollback_call_count=0,
        delete_call_count=0,
        post_delete_history_read_count=0,
        exact_send_receipt_obtained=True,
        exact_send_receipt_used_for_verification=True,
        fixture_reply_present_same_session=True,
        fixture_reply_preserved=True,
    )


def probes():
    return (
        Probe(InjectedConfirmation(True, FIRST_CONFIRMATION_SCOPE)),
        Probe(InjectedFreshPreflightEvidence()),
        Probe(InjectedManualRemovalEvidence(True, MANUAL_REMOVAL_SCOPE)),
        Probe(InjectedConfirmation(True, SECOND_CONFIRMATION_SCOPE)),
        Probe(verified_roundtrip()),
    )


def coordinator(items, *, timeout_seconds=300):
    return DormantTwoConfirmationCoordinator(
        plan=build_protected_real_roundtrip_plan(),
        first_confirmation_reader=items[0],
        preflight_probe=items[1],
        manual_evidence_reader=items[2],
        second_confirmation_reader=items[3],
        exact_scope_probe=items[4],
        timeout_seconds=timeout_seconds,
    )


class DormantConfirmationCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_sequence_reaches_only_fixture_scope_probe(self):
        items = probes()
        result = await coordinator(items).run_once()

        self.assertEqual(result.state, "PREPARED")
        self.assertTrue(result.exact_scope_verified_in_doubles)
        self.assertEqual([item.calls for item in items], [1, 1, 1, 1, 1])
        self.assertTrue(result.private_state_cleared)
        self.assertFalse(result.m63_drafts_consumed)
        self.assertFalse(result.real_execution_enabled)
        self.assertEqual(result.external_calls, 0)

    async def test_first_rejection_stops_before_preflight_and_scope(self):
        items = list(probes())
        items[0] = Probe(InjectedConfirmation(False, FIRST_CONFIRMATION_SCOPE))
        result = await coordinator(items).run_once()

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.reason, "dormant_first_confirmation_rejected")
        self.assertEqual([item.calls for item in items], [1, 0, 0, 0, 0])

    async def test_preflight_drift_stops_before_manual_and_scope(self):
        items = list(probes())
        items[1] = Probe(replace(InjectedFreshPreflightEvidence(), chat_id=99999))
        result = await coordinator(items).run_once()

        self.assertEqual(result.reason, "dormant_preflight_drift_rejected")
        self.assertEqual([item.calls for item in items], [1, 1, 0, 0, 0])

    async def test_manual_evidence_and_second_rejection_stop_before_scope(self):
        for index, replacement, reason in (
            (
                2,
                InjectedManualRemovalEvidence(False, MANUAL_REMOVAL_SCOPE),
                "dormant_manual_evidence_rejected",
            ),
            (
                3,
                InjectedConfirmation(False, SECOND_CONFIRMATION_SCOPE),
                "dormant_second_confirmation_rejected",
            ),
        ):
            with self.subTest(index=index):
                items = list(probes())
                items[index] = Probe(replacement)
                result = await coordinator(items).run_once()
                self.assertEqual(result.reason, reason)
                self.assertEqual(items[4].calls, 0)

    async def test_timeout_and_cancellation_are_terminal_before_scope(self):
        for error, expected_state, expected_reason in (
            (
                asyncio.TimeoutError(),
                "NO-GO",
                "dormant_confirmation_timeout_terminal",
            ),
            (
                asyncio.CancelledError(),
                "CANCELLED",
                "dormant_confirmation_cancelled_terminal",
            ),
        ):
            with self.subTest(expected_state=expected_state):
                items = list(probes())
                items[1] = Probe(error=error)
                result = await coordinator(items).run_once()
                self.assertEqual(result.state, expected_state)
                self.assertEqual(result.reason, expected_reason)
                self.assertEqual(items[4].calls, 0)
                self.assertTrue(result.private_state_cleared)

    async def test_reuse_is_rejected_without_any_additional_probe(self):
        items = probes()
        owner = coordinator(items)
        first = await owner.run_once()
        second = await owner.run_once()

        self.assertEqual(first.state, "PREPARED")
        self.assertEqual(second.state, "NO-GO")
        self.assertEqual(second.reason, "dormant_confirmation_reuse_rejected")
        self.assertEqual([item.calls for item in items], [1, 1, 1, 1, 1])

    def test_no_real_source_command_client_or_message_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_dormant_confirmation_coordinator.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env",
            "httpx",
            "pymongo",
            "niaclient(",
            "bitrixclient(",
            "send_approved_text(",
            "send_approved_message(",
            "get_dialog(",
            "get_session_history(",
            "argparse",
            "input(",
            "subprocess",
            "socket",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
