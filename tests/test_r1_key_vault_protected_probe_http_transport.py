import unittest

import httpx

from bitrix_connector.r1_key_vault_protected_probe_http_transport import (
    MAX_RESPONSE_BYTES,
    ExactOneShotProtectedProbeHttpTransport,
    ProtectedProbeTransportFailure,
    build_dormant_production_http_transport,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_owner import (
    PROBE_ENDPOINT,
    REQUEST_TIMEOUT_SECONDS,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_policy import (
    EXPECTED_PACKAGES,
)


TOKEN = bytearray(b"fixture-review-token-long-enough")


def evidence():
    return {
        "schema": "nia-next-r1-host-probe-v1",
        "packages": dict(EXPECTED_PACKAGES),
        "setting_present": False,
        "setting_valid": None,
        "external_calls": 0,
        "writes": 0,
    }


class R1KeyVaultProtectedProbeHttpTransportTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_exact_get_is_one_shot_without_redirect_or_retry(self):
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.method, "GET")
            self.assertEqual(str(request.url), PROBE_ENDPOINT)
            self.assertEqual(
                request.headers["Authorization"],
                "Bearer fixture-review-token-long-enough",
            )
            self.assertEqual(request.headers["Accept"], "application/json")
            return httpx.Response(200, json=evidence())

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = ExactOneShotProtectedProbeHttpTransport(client=client)
        response = await transport.get_exact_once(
            url=PROBE_ENDPOINT,
            bearer_token=bytearray(TOKEN),
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        await transport.close()
        await client.aclose()

        self.assertEqual(len(calls), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload, evidence())
        with self.assertRaisesRegex(RuntimeError, "request_contract_invalid"):
            await transport.get_exact_once(
                url=PROBE_ENDPOINT,
                bearer_token=bytearray(TOKEN),
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            )

    async def test_redirect_is_returned_without_following(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={"Location": "https://example.invalid"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = ExactOneShotProtectedProbeHttpTransport(client=client)
        response = await transport.get_exact_once(
            url=PROBE_ENDPOINT,
            bearer_token=bytearray(TOKEN),
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        await client.aclose()
        self.assertEqual((len(calls), response.status_code), (1, 302))

    async def test_invalid_duplicate_or_oversized_body_becomes_drift_payload(self):
        bodies = (
            b"not-json",
            b'{"detail":"a","detail":"b"}',
            b"x" * (MAX_RESPONSE_BYTES + 1),
        )
        for body in bodies:
            with self.subTest(size=len(body)):
                client = httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda _request: httpx.Response(200, content=body)
                    )
                )
                transport = ExactOneShotProtectedProbeHttpTransport(client=client)
                response = await transport.get_exact_once(
                    url=PROBE_ENDPOINT,
                    bearer_token=bytearray(TOKEN),
                    timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                    follow_redirects=False,
                )
                await client.aclose()
                self.assertIsNone(response.payload)

    async def test_transport_error_is_sanitized_and_terminal(self):
        def handler(request):
            raise httpx.ConnectError("private endpoint detail", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transport = ExactOneShotProtectedProbeHttpTransport(client=client)
        with self.assertRaisesRegex(
            ProtectedProbeTransportFailure, "r1_probe_transport_ambiguous"
        ) as raised:
            await transport.get_exact_once(
                url=PROBE_ENDPOINT,
                bearer_token=bytearray(TOKEN),
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        await client.aclose()
        self.assertNotIn("private", repr(raised.exception))

    async def test_inert_production_builder_can_close_without_request(self):
        transport = build_dormant_production_http_transport()
        self.assertEqual(repr(transport), "ExactOneShotProtectedProbeHttpTransport(<redacted>)")
        await transport.close()


if __name__ == "__main__":
    unittest.main()
