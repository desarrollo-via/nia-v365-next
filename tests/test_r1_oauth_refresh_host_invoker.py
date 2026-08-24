import unittest

from bitrix_connector.r1_oauth_refresh_host_invoker import (
    invoke_r1_oauth_refresh_from_host_once,
)


class R1OAuthRefreshHostInvokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_token_and_one_exact_endpoint_request(self):
        calls = []
        async def token_provider():
            calls.append("token")
            return "fixture-jwt"
        async def endpoint(path, token):
            calls.append((path, token))
            return 200
        result = await invoke_r1_oauth_refresh_from_host_once(
            token_provider=token_provider, endpoint_caller=endpoint
        )
        self.assertEqual(result.state, "READY")
        self.assertEqual(result.token_requests, 1)
        self.assertEqual(result.endpoint_requests, 1)
        self.assertEqual(calls[0], "token")
        self.assertEqual(calls[1][0], "/bitrix-connector/r1/oauth-refresh")

    async def test_invalid_token_does_not_call_endpoint(self):
        calls = 0
        async def endpoint(path, token):
            nonlocal calls
            calls += 1
            return 200
        result = await invoke_r1_oauth_refresh_from_host_once(
            token_provider=lambda: _empty_token(), endpoint_caller=endpoint
        )
        self.assertEqual(result.reason, "identity_token_rejected")
        self.assertEqual(calls, 0)


async def _empty_token():
    return ""


if __name__ == "__main__":
    unittest.main()
