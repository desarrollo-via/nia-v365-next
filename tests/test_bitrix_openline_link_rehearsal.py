import unittest
import asyncio
from datetime import datetime, timedelta, timezone

from bitrix_connector.config import load_settings
from bitrix_connector.openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    LinkRehearsalStatus,
    rehearse_controlled_link,
)
from bitrix_connector.openline_r0_receipt import ControlledR0Receipt
from bitrix_connector.openline_pilot_preflight import (
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    build_controlled_pilot_preview,
)


NOW = datetime(2026, 7, 27, 15, 0, tzinfo=timezone.utc)
MEMBER_ID = "member-controlled"


def snapshot(bot_id=245339):
    return OpenLineConfigSnapshot.model_validate({
        "ID": 13,
        "LINE_NAME": "WhatApp Wazzup OFICIAL",
        "ACTIVE": "Y",
        "WELCOME_BOT_ENABLE": "Y",
        "WELCOME_BOT_JOIN": "always",
        "WELCOME_BOT_ID": bot_id,
        "WELCOME_BOT_TIME": 0,
        "WELCOME_BOT_LEFT": "close",
        "NO_ANSWER_BOT_ID": 0,
        "CLOSE_BOT_ID": 0,
        "AUTO_CLOSE_BOT_ID": 0,
        "WORKTIME_DAYOFF_BOT_ID": 0,
    })


def preview(*, chat_id=78733, dialog_id="chat78733"):
    preflight = OpenLinePreflightResult(
        status=OpenLinePreflightStatus.READY,
        reason="openline_snapshot_ready",
        chat_id=chat_id,
        dialog_id=dialog_id,
        config=snapshot(),
    )
    return build_controlled_pilot_preview(
        preflight=preflight,
        bot_id=CONTROLLED_BOT_ID,
        member_id=MEMBER_ID,
        webhook_url="https://nia.example.com/bitrix-connector/webhook",
        valid_from=NOW - timedelta(minutes=2),
        valid_until=NOW + timedelta(minutes=8),
    )


def receipt():
    return ControlledR0Receipt(
        event_key="a" * 64,
        member_id=MEMBER_ID,
        bot_id=CONTROLLED_BOT_ID,
        chat_id=78733,
        dialog_id="chat78733",
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        identity_verified=True,
        persisted=False,
        nia_called=False,
        bitrix_written=False,
    )


def off_settings():
    return load_settings({"NIA_BITRIX_MODE": "active"})


class InMemoryLine:
    def __init__(self):
        self.current = snapshot()
        self.calls = []
        self.fail_link_after_apply = False
        self.reject_rollback = False

    async def read(self):
        return self.current

    async def update(self, contract):
        self.calls.append(contract)
        if len(self.calls) == 2 and self.reject_rollback:
            return False
        values = contract.payload.PARAMS
        self.current = snapshot(values.WELCOME_BOT_ID)
        if len(self.calls) == 1 and self.fail_link_after_apply:
            raise RuntimeError("simulated transport loss")
        return True


class ControlledLinkRehearsalTests(unittest.IsolatedAsyncioTestCase):
    async def test_links_probes_off_and_always_restores(self):
        line = InMemoryLine()
        probes = 0

        async def probe():
            nonlocal probes
            probes += 1
            return receipt()

        result = await rehearse_controlled_link(
            preview=preview(),
            settings=off_settings(),
            expected_member_id=MEMBER_ID,
            update=line.update,
            read_snapshot=line.read,
            receipt_waiter=probe,
            receipt_timeout_seconds=1,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.RESTORED)
        self.assertEqual((result.link_attempts, result.rollback_attempts), (1, 1))
        self.assertTrue(result.link_verified)
        self.assertTrue(result.off_verified)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(probes, 1)
        self.assertEqual(line.current.welcome_bot_id, 245339)
        self.assertEqual(
            [call.payload.PARAMS.WELCOME_BOT_ID for call in line.calls],
            [CONTROLLED_BOT_ID, 245339],
        )
        self.assertTrue(all(not call.executable for call in line.calls))
        self.assertTrue(all(
            call.method == "imopenlines.config.update"
            for call in line.calls
        ))

    async def test_transport_loss_after_link_still_rolls_back(self):
        line = InMemoryLine()
        line.fail_link_after_apply = True

        result = await rehearse_controlled_link(
            preview=preview(),
            settings=off_settings(),
            expected_member_id=MEMBER_ID,
            update=line.update,
            read_snapshot=line.read,
            receipt_waiter=lambda: None,
            receipt_timeout_seconds=1,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.FAILED_RESTORED)
        self.assertEqual(result.reason, "link_rehearsal_operation_failed")
        self.assertTrue(result.rollback_verified)
        self.assertEqual(line.current.welcome_bot_id, 245339)
        self.assertEqual(len(line.calls), 2)

    async def test_rejects_wrong_scope_or_expired_window_before_update(self):
        cases = (
            (preview(chat_id=78734, dialog_id="chat78734"), NOW),
            (preview(), NOW + timedelta(minutes=9)),
        )
        for contract, instant in cases:
            with self.subTest(instant=instant):
                line = InMemoryLine()
                result = await rehearse_controlled_link(
                    preview=contract,
                    settings=off_settings(),
                    expected_member_id=MEMBER_ID,
                    update=line.update,
                    read_snapshot=line.read,
                    receipt_waiter=lambda: None,
                    receipt_timeout_seconds=1,
                    clock=lambda current=instant: current,
                )
                self.assertEqual(result.status, LinkRehearsalStatus.BLOCKED)
                self.assertEqual(
                    result.reason,
                    "link_rehearsal_scope_or_window_invalid",
                )
                self.assertEqual(line.calls, [])

    async def test_snapshot_drift_blocks_before_update(self):
        line = InMemoryLine()
        line.current = snapshot(bot_id=999999)

        result = await rehearse_controlled_link(
            preview=preview(),
            settings=off_settings(),
            expected_member_id=MEMBER_ID,
            update=line.update,
            read_snapshot=line.read,
            receipt_waiter=lambda: None,
            receipt_timeout_seconds=1,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.BLOCKED)
        self.assertEqual(result.reason, "link_rehearsal_snapshot_not_original")
        self.assertEqual(line.calls, [])

    async def test_rollback_rejection_is_terminal_and_visible(self):
        line = InMemoryLine()
        line.reject_rollback = True

        async def probe():
            return receipt()

        result = await rehearse_controlled_link(
            preview=preview(),
            settings=off_settings(),
            expected_member_id=MEMBER_ID,
            update=line.update,
            read_snapshot=line.read,
            receipt_waiter=probe,
            receipt_timeout_seconds=1,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.ROLLBACK_FAILED)
        self.assertEqual(result.reason, "link_rehearsal_rollback_rejected")
        self.assertFalse(result.rollback_verified)
        self.assertEqual(line.current.welcome_bot_id, CONTROLLED_BOT_ID)

    async def test_receipt_timeout_always_restores_original_bot(self):
        line = InMemoryLine()

        async def never_receives():
            await asyncio.Future()

        result = await rehearse_controlled_link(
            preview=preview(),
            settings=off_settings(),
            expected_member_id=MEMBER_ID,
            update=line.update,
            read_snapshot=line.read,
            receipt_waiter=never_receives,
            receipt_timeout_seconds=0.01,
            clock=lambda: NOW,
        )

        self.assertEqual(result.status, LinkRehearsalStatus.FAILED_RESTORED)
        self.assertEqual(result.reason, "link_rehearsal_receipt_timeout")
        self.assertFalse(result.receipt_verified)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(line.current.welcome_bot_id, 245339)


if __name__ == "__main__":
    unittest.main()
