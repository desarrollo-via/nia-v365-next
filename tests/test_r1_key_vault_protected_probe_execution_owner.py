import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import httpx

from bitrix_connector.r1_key_vault_protected_probe_dotenv_source import (
    ExactReviewTokenDotenvSource,
)
from bitrix_connector.r1_key_vault_protected_probe_execution_owner import (
    REAL_CONFIRMATION,
    ProtectedProbeExecutionSnapshot,
    execute_protected_probe_once,
    main,
)
from bitrix_connector.r1_key_vault_protected_probe_http_transport import (
    ExactOneShotProtectedProbeHttpTransport,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_owner import (
    REVIEW_TOKEN_NAME,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_policy import (
    EXPECTED_PACKAGES,
    ProtectedProbeInvocationState,
)


TOKEN = b"fixture-review-token-long-enough"


def evidence():
    return {
        "schema": "nia-next-r1-host-probe-v1",
        "packages": dict(EXPECTED_PACKAGES),
        "setting_present": False,
        "setting_valid": None,
        "external_calls": 0,
        "writes": 0,
    }


class R1KeyVaultProtectedProbeExecutionOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_owner_lifecycle_uses_fixture_file_and_mock_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_bytes(REVIEW_TOKEN_NAME.encode() + b"=" + TOKEN + b"\n")
            source = ExactReviewTokenDotenvSource(path, expected_path=path)
            calls = []

            def handler(request):
                calls.append(request)
                return httpx.Response(200, json=evidence())

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            transport = ExactOneShotProtectedProbeHttpTransport(client=client)
            result = await execute_protected_probe_once(
                dotenv_path=path,
                source=source,
                transport=transport,
            )
            await client.aclose()

        self.assertEqual(
            result.state,
            ProtectedProbeInvocationState.VERIFIED_ABSENT.value,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            (result.source_read_calls, result.request_calls, result.real_network_calls),
            (1, 1, 1),
        )
        self.assertTrue(result.token_cleared)
        self.assertTrue(result.source_closed)
        self.assertTrue(result.transport_closed)
        self.assertNotIn(TOKEN.decode(), repr(result))

    def test_cli_rejects_wrong_request_without_executor(self):
        calls = []
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(("--confirm-code", "wrong"), executor=lambda **kwargs: calls.append(kwargs))
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertIn("NO-GO-OWNER-REJECTED", output.getvalue())

    def test_cli_emits_only_sanitized_snapshot(self):
        async def executor(**_kwargs):
            return ProtectedProbeExecutionSnapshot(
                state=ProtectedProbeInvocationState.VERIFIED_ABSENT.value,
                protected_source_opened=True,
                source_read_calls=1,
                request_calls=1,
                real_network_calls=1,
                token_cleared=True,
                source_closed=True,
                transport_closed=True,
            )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                (
                    "--confirm-code",
                    REAL_CONFIRMATION,
                    "--dotenv-path",
                    ".env",
                ),
                executor=executor,
            )
        self.assertEqual(code, 0)
        self.assertNotIn(TOKEN.decode(), output.getvalue())
        self.assertIn('"request_calls": 1', output.getvalue())


if __name__ == "__main__":
    unittest.main()
