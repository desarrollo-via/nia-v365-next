import asyncio
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from bitrix_connector.config import load_settings
from bitrix_connector.g0_entrypoint import G0_WEBHOOK_PATH, create_g0_entrypoint
from bitrix_connector.openline_r0_receipt import ControlledR0ReceiptGate
from bitrix_connector.pilot_scope import PilotScopeRule


NOW = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)


def settings():
    return load_settings({
        "NIA_BITRIX_MODE": "active",
        "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
        "NIA_BITRIX_MEMBER_ID": "member-controlled",
        "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
    })


def form(*, chat_id=78733, dialog_id="chat78733"):
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "373259",
        "data[message][id]": "9001",
        "data[message][chatId]": str(chat_id),
        "data[message][authorId]": "27",
        "data[message][text]": "mensaje controlado",
        "data[chat][dialogId]": dialog_id,
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": "member-controlled",
        "auth[application_token]": "application-secret",
    }


def rule():
    return PilotScopeRule(
        member_id="member-controlled",
        bot_id=373259,
        chat_id=78733,
        dialog_id="chat78733",
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=9),
    )


class ControlledR0ReceiptGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_g0_handler_resolves_only_exact_inert_receipt(self):
        gate = ControlledR0ReceiptGate(clock=lambda: NOW)
        await gate.arm(rule())
        app = create_g0_entrypoint(
            public_origin="https://nia.example.test",
            settings_loader=settings,
            receipt_observer=gate.observe,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="https://nia.example.test",
        ) as client:
            wrong = await client.post(
                G0_WEBHOOK_PATH,
                data=form(chat_id=78734, dialog_id="chat78734"),
            )
            self.assertEqual(wrong.status_code, 200)
            self.assertFalse(gate._future.done())

            exact = await client.post(G0_WEBHOOK_PATH, data=form())
            self.assertEqual(exact.status_code, 200)
            receipt = await asyncio.wait_for(gate.wait(), timeout=0.1)

        self.assertEqual(receipt.member_id, "member-controlled")
        self.assertEqual(receipt.bot_id, 373259)
        self.assertEqual(receipt.chat_id, 78733)
        self.assertEqual(receipt.dialog_id, "chat78733")
        self.assertEqual(receipt.effective_mode, "off")
        self.assertTrue(receipt.identity_verified)
        self.assertFalse(receipt.persisted)
        self.assertFalse(receipt.nia_called)
        self.assertFalse(receipt.bitrix_written)
        self.assertNotIn("mensaje controlado", repr(receipt))
        self.assertNotIn("application-secret", repr(receipt))
        await gate.close()

    async def test_wait_is_cancellable_and_close_is_idempotent(self):
        gate = ControlledR0ReceiptGate(clock=lambda: NOW)
        await gate.arm(rule())
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(gate.wait(), timeout=0.01)
        await gate.close()
        await gate.close()


if __name__ == "__main__":
    unittest.main()
