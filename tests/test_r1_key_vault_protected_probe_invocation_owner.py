import unittest
from pathlib import Path

from bitrix_connector.r1_key_vault_protected_probe_invocation_owner import (
    FIXTURE_AUTHORIZATION,
    HELPER_FAILED,
    HELPER_REMAINDER,
    PROBE_ENDPOINT,
    REVIEW_TOKEN_NAME,
    REQUEST_TIMEOUT_SECONDS,
    FixtureOnlyProtectedProbeInvocationOwner,
    FixtureProbeHttpResponse,
)
from bitrix_connector.r1_key_vault_protected_probe_invocation_policy import (
    EXPECTED_PACKAGES,
    ProtectedProbeInvocationState,
)


ROOT = Path(__file__).resolve().parents[1]
TOKEN = b"fixture-review-token-long-enough"


def evidence(*, present=False, valid=None):
    return {
        "schema": "nia-next-r1-host-probe-v1",
        "packages": dict(EXPECTED_PACKAGES),
        "setting_present": present,
        "setting_valid": valid,
        "external_calls": 0,
        "writes": 0,
    }


class SourceDouble:
    kind = "fixture-double"

    def __init__(self, token=TOKEN, fail=False, close_fail=False):
        self.token = token
        self.fail = fail
        self.close_fail = close_fail
        self.calls = []
        self.issued = None

    async def open(self):
        self.calls.append("open")
        if self.fail:
            raise RuntimeError("private source failure")

    async def read_exact(self, name):
        self.calls.append(("read", name))
        self.issued = bytearray(self.token)
        return self.issued

    async def close(self):
        self.calls.append("close")
        if self.close_fail:
            raise RuntimeError("private close failure")


class TransportDouble:
    kind = "fixture-double"

    def __init__(self, response=None, fail=False, close_fail=False):
        self.response = response or FixtureProbeHttpResponse(200, evidence())
        self.fail = fail
        self.close_fail = close_fail
        self.calls = []

    async def get_exact_once(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("private transport failure")
        self.asserted_token = bytes(kwargs["bearer_token"])
        return self.response

    async def close(self):
        self.calls.append("close")
        if self.close_fail:
            raise RuntimeError("private close failure")


class R1KeyVaultProtectedProbeInvocationOwnerTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_exact_fixture_lifecycle_is_one_shot_and_sanitized(self):
        source = SourceDouble()
        transport = TransportDouble()
        owner = FixtureOnlyProtectedProbeInvocationOwner(
            source=source, transport=transport
        )
        self.assertEqual((source.calls, transport.calls), ([], []))

        result = await owner.execute_once(FIXTURE_AUTHORIZATION)

        self.assertEqual(
            result.state,
            ProtectedProbeInvocationState.VERIFIED_ABSENT.value,
        )
        self.assertEqual(source.calls, ["open", ("read", REVIEW_TOKEN_NAME), "close"])
        request = transport.calls[0]
        self.assertEqual(request["url"], PROBE_ENDPOINT)
        self.assertEqual(request["timeout_seconds"], REQUEST_TIMEOUT_SECONDS)
        self.assertFalse(request["follow_redirects"])
        self.assertEqual(transport.asserted_token, TOKEN)
        self.assertEqual(source.issued, bytearray())
        self.assertEqual(
            (
                result.credential_source_reads,
                result.transport_calls,
                result.retries,
                result.redirects_followed,
                result.real_network_calls,
            ),
            (1, 1, 0, 0, 0),
        )
        self.assertTrue(result.secret_cleared)
        self.assertTrue(result.source_closed)
        self.assertTrue(result.transport_closed)
        with self.assertRaisesRegex(RuntimeError, "reuse_or_auth_invalid"):
            await owner.execute_once(FIXTURE_AUTHORIZATION)

    async def test_present_baseline_is_classified_without_value(self):
        transport = TransportDouble(
            FixtureProbeHttpResponse(200, evidence(present=True, valid=True))
        )
        result = await FixtureOnlyProtectedProbeInvocationOwner(
            source=SourceDouble(), transport=transport
        ).execute_once(FIXTURE_AUTHORIZATION)
        self.assertEqual(
            result.state,
            ProtectedProbeInvocationState.VERIFIED_PRESENT.value,
        )
        self.assertNotIn(TOKEN.decode(), repr(result))

    async def test_allowlisted_http_failure_is_classified(self):
        transport = TransportDouble(
            FixtureProbeHttpResponse(401, {"detail": "review_unauthorized"})
        )
        result = await FixtureOnlyProtectedProbeInvocationOwner(
            source=SourceDouble(), transport=transport
        ).execute_once(FIXTURE_AUTHORIZATION)
        self.assertEqual(
            result.state,
            ProtectedProbeInvocationState.AUTH_REJECTED_NOT_CONSUMED.value,
        )

    async def test_source_or_transport_failure_is_redacted_and_closed(self):
        for source, transport, expected_counts in (
            (SourceDouble(fail=True), TransportDouble(), (0, 0)),
            (SourceDouble(), TransportDouble(fail=True), (1, 1)),
        ):
            with self.subTest(expected_counts=expected_counts):
                result = await FixtureOnlyProtectedProbeInvocationOwner(
                    source=source, transport=transport
                ).execute_once(FIXTURE_AUTHORIZATION)
                self.assertEqual(result.state, HELPER_FAILED)
                self.assertEqual(
                    (result.credential_source_reads, result.transport_calls),
                    expected_counts,
                )
                self.assertTrue(result.source_closed)
                self.assertTrue(result.transport_closed)
                self.assertNotIn("private", repr(result))

    async def test_close_failure_is_terminal_remainder(self):
        result = await FixtureOnlyProtectedProbeInvocationOwner(
            source=SourceDouble(close_fail=True),
            transport=TransportDouble(),
        ).execute_once(FIXTURE_AUTHORIZATION)
        self.assertEqual(result.state, HELPER_REMAINDER)
        self.assertFalse(result.source_closed)
        self.assertTrue(result.transport_closed)

    async def test_wrong_authorization_does_not_open_or_consume_doubles(self):
        source = SourceDouble()
        transport = TransportDouble()
        owner = FixtureOnlyProtectedProbeInvocationOwner(
            source=source, transport=transport
        )
        with self.assertRaisesRegex(RuntimeError, "reuse_or_auth_invalid"):
            await owner.execute_once("wrong")
        self.assertEqual((source.calls, transport.calls), ([], []))
        result = await owner.execute_once(FIXTURE_AUTHORIZATION)
        self.assertEqual(
            result.state,
            ProtectedProbeInvocationState.VERIFIED_ABSENT.value,
        )

    def test_real_or_unmarked_dependencies_are_rejected(self):
        source = SourceDouble()
        transport = TransportDouble()
        source.kind = "real"
        with self.assertRaisesRegex(TypeError, "source_not_fixture_double"):
            FixtureOnlyProtectedProbeInvocationOwner(
                source=source, transport=transport
            )
        source.kind = "fixture-double"
        transport.kind = "real"
        with self.assertRaisesRegex(TypeError, "transport_not_fixture_double"):
            FixtureOnlyProtectedProbeInvocationOwner(
                source=source, transport=transport
            )

    def test_owner_has_no_real_source_network_or_output_surface(self):
        text = (
            ROOT
            / "bitrix_connector"
            / "r1_key_vault_protected_probe_invocation_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "credentialmanager",
            "allowlisteddotenvsource",
            "httpx",
            "requests",
            "aiohttp",
            "subprocess",
            "socket",
            "print(",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
