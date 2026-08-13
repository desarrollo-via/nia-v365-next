import json
import unittest

import httpx

from bitrix_connector.r1_remote_session_http_client import (
    ExactR1RemoteSessionHttpClient,
)


class ExactR1RemoteSessionHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_exact_routes_and_redacted_auth(self):
        requests = []

        async def handler(request):
            requests.append(request)
            states = {
                "/first-confirmation": "AWAITING-SECOND-CONFIRMATION",
                "/second-confirmation": "ATTENTION-REQUIRED",
                "/status": "VERIFIED",
                "/session": "DISARMED",
            }
            suffix = request.url.path.rsplit("/", 1)[-1]
            suffix = f"/{suffix}"
            return httpx.Response(200, json={
                "state": states[suffix], "consumed": False
            })

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = ExactR1RemoteSessionHttpClient(
            public_origin="https://example.test", review_token="x" * 24,
            http_client=http,
        )
        await client.first_confirmation_once("one")
        await client.second_confirmation_once("two")
        await client.status_once()
        await client.disarm_once()
        self.assertEqual([request.method for request in requests], [
            "POST", "POST", "GET", "DELETE"
        ])
        self.assertTrue(all(
            request.url.path.startswith("/bitrix-connector/internal/r1-event/")
            for request in requests
        ))
        self.assertEqual(
            json.loads(requests[0].content), {"confirmation": "one"}
        )
        self.assertNotIn("x" * 24, repr(client))
        await client.close()
        await http.aclose()

    async def test_invalid_origin_token_and_response_fail_closed(self):
        with self.assertRaises(ValueError):
            ExactR1RemoteSessionHttpClient(
                public_origin="http://example.test", review_token="x" * 24
            )
        with self.assertRaises(ValueError):
            ExactR1RemoteSessionHttpClient(
                public_origin="https://example.test", review_token="short"
            )
        http = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": True})
        ))
        client = ExactR1RemoteSessionHttpClient(
            public_origin="https://example.test", review_token="x" * 24,
            http_client=http,
        )
        with self.assertRaisesRegex(RuntimeError, "response_invalid"):
            await client.status_once()
        await client.close()
        await http.aclose()


if __name__ == "__main__":
    unittest.main()
