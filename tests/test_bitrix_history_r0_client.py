import json
import unittest

import httpx

from bitrix_connector.bitrix_history_r0_client import (
    BITRIX_DIALOG_GET_PATH,
    BITRIX_SESSION_HISTORY_GET_PATH,
    MAX_HISTORY_RESPONSE_BYTES,
    BitrixHistoryR0Client,
    BitrixHistoryReadDecision,
)


def dialog_payload(last_message_id=700):
    return {
        "id": 78733,
        "dialog_id": "chat78733",
        "entity_type": "LINES",
        "entity_data_1": "a|b|c|d|e|900",
        "role": "guest",
        "last_message_id": last_message_id,
        "name": "dato no proyectado",
    }


def history_payload():
    return {
        "chatId": 78733,
        "sessionId": 900,
        "message": [{
            "id": 701,
            "chatid": 78733,
            "senderid": 51,
            "recipientid": "chat78733",
            "date": "2026-07-31T15:00:01+00:00",
            "text": "mensaje controlado",
        }],
        "users": [{"id": 51, "connector": True}],
    }


class BitrixHistoryR0ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_only_two_reads_and_uses_fixed_endpoints(self):
        captured = []

        async def handler(request):
            captured.append((request.url.path, json.loads(request.content)))
            if request.url.path.endswith(BITRIX_DIALOG_GET_PATH):
                return httpx.Response(200, json={"result": dialog_payload()})
            return httpx.Response(200, json={"result": history_payload()})

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        client = BitrixHistoryR0Client(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=10,
            http_client=http_client,
        )
        dialog = await client.get_dialog("chat78733")
        history = await client.get_session_history(dialog.dialog.session_id)

        self.assertEqual(dialog.decision, BitrixHistoryReadDecision.SUCCESS)
        self.assertEqual(history.decision, BitrixHistoryReadDecision.SUCCESS)
        self.assertEqual(captured, [
            (BITRIX_DIALOG_GET_PATH, {
                "CHAT_ID": 78733,
                "auth": "oauth-secret-token",
            }),
            (BITRIX_SESSION_HISTORY_GET_PATH, {
                "SESSION_ID": 900,
                "auth": "oauth-secret-token",
            }),
        ])
        self.assertNotIn("oauth-secret-token", repr(dialog))
        self.assertNotIn("dato no proyectado", repr(dialog))
        public = {
            name for name in dir(BitrixHistoryR0Client)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"close", "get_dialog", "get_session_history"})

    async def test_fails_closed_on_oversized_or_remote_response(self):
        cases = (
            (
                httpx.Response(200, content=b"x" * (MAX_HISTORY_RESPONSE_BYTES + 1)),
                "bitrix_history_response_too_large",
            ),
            (
                httpx.Response(401, json={
                    "error": "expired_token",
                    "error_description": "oauth-secret-token",
                }),
                "bitrix_history_token_expired",
            ),
            (httpx.Response(429), "bitrix_history_read_unavailable"),
        )
        for response, expected in cases:
            with self.subTest(expected=expected):
                async def handler(request, current=response):
                    return current

                http_client = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
                self.addAsyncCleanup(http_client.aclose)
                client = BitrixHistoryR0Client(
                    portal_url="https://portal.bitrix24.test",
                    access_token="oauth-secret-token",
                    timeout_seconds=10,
                    http_client=http_client,
                )
                result = await client.get_session_history(900)
                self.assertEqual(result.decision, BitrixHistoryReadDecision.FAIL)
                self.assertEqual(result.error_code, expected)
                self.assertNotIn("oauth-secret-token", repr(result))


if __name__ == "__main__":
    unittest.main()
