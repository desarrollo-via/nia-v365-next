import asyncio
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from bitrix_connector.r1_oauth_refresh_execution_owner import (
    R1OAuthRefreshSnapshot,
    R1_OAUTH_REFRESH_CONFIRMATION,
    execute_r1_oauth_refresh_protected_once,
    execute_r1_oauth_refresh_once,
    main,
)
from bitrix_connector.r1_key_vault_exact_secret_backend import (
    build_managed_identity_exact_secret_backend,
)


class Backend:
    async def fetch_exact(self, _target):
        raise AssertionError("the protected helper owns this call")

    async def close(self):
        return None


class Provider:
    def __init__(self, *, persist=True):
        self.current = "stale"
        self.persist = persist
        self.refresh_calls = 0

    async def get_access_token(self, _member):
        return self.current

    async def refresh_access_token(self, _member, stale):
        self.refresh_calls += 1
        if stale != self.current:
            raise AssertionError("stale token mismatch")
        if self.persist:
            self.current = "fresh"
        return "fresh"


class Resources:
    member_id = "fixture-member"

    def __init__(self, provider):
        self.oauth_provider = provider
        self.closed = 0

    async def close(self):
        self.closed += 1


class Factory:
    def __init__(self, resources):
        self.resources = resources
        self.calls = 0

    async def build(self, _settings, *, timeout_seconds):
        self.calls += 1
        self.assert_timeout = timeout_seconds
        return self.resources


class OwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_binding_constructs_and_closes_without_secret_read(self):
        backend = build_managed_identity_exact_secret_backend(
            vault_url="https://nia-next-r1-kv-260810.vault.azure.net"
        )
        await backend.close()

    async def test_missing_async_transport_stops_before_binding(self):
        with patch(
            "bitrix_connector.r1_oauth_refresh_execution_owner.find_spec",
            return_value=None,
        ), patch(
            "bitrix_connector.r1_oauth_refresh_execution_owner."
            "build_managed_identity_exact_secret_backend",
        ) as build:
            snapshot = await execute_r1_oauth_refresh_protected_once()
        self.assertEqual(snapshot.reason, "r1_oauth_refresh_async_transport_missing")
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.source_read_calls, 0)
        build.assert_not_called()

    async def test_rotates_once_verifies_and_closes(self):
        provider = Provider()
        resources = Resources(provider)

        async def builder():
            return resources

        snapshot = await execute_r1_oauth_refresh_once(
            credential_backend=Backend(), resources_factory=Factory(resources),
            resources_builder=builder,
        )
        self.assertEqual(snapshot.state, "READY")
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual(snapshot.refresh_calls, 1)
        self.assertEqual(snapshot.persistence_verification_calls, 1)
        self.assertEqual(resources.closed, 1)

    async def test_unverified_persistence_stops_closed(self):
        resources = Resources(Provider(persist=False))

        async def builder():
            return resources

        snapshot = await execute_r1_oauth_refresh_once(
            credential_backend=Backend(), resources_factory=Factory(resources),
            resources_builder=builder,
        )
        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "r1_oauth_refresh_persistence_unverified")
        self.assertTrue(snapshot.resources_closed)

    async def test_invalid_dependencies_stop_before_protected_source(self):
        snapshot = await execute_r1_oauth_refresh_once(
            credential_backend=None, resources_factory=None
        )
        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.source_read_calls, 0)
        self.assertEqual(snapshot.refresh_calls, 0)

    async def test_source_failure_is_sanitized(self):
        class FailingBackend(Backend):
            async def fetch_exact(self, _target):
                raise RuntimeError("private")

        snapshot = await execute_r1_oauth_refresh_once(
            credential_backend=FailingBackend(), resources_factory=Factory(Resources(Provider()))
        )
        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "r1_oauth_refresh_failed_safe")
        self.assertEqual(snapshot.refresh_calls, 0)


class OwnerCliTests(unittest.TestCase):
    def test_rejected_request_does_not_start_executor(self):
        called = 0

        async def executor():
            nonlocal called
            called += 1
            return R1OAuthRefreshSnapshot(state="READY")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--confirm-code", "wrong"], executor=executor)
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(called, 0)
        self.assertEqual(payload["reason"], "r1_oauth_refresh_owner_rejected")

    def test_valid_request_emits_only_snapshot(self):
        async def executor():
            return R1OAuthRefreshSnapshot(state="READY", reason="fixture")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                ["--confirm-code", R1_OAUTH_REFRESH_CONFIRMATION], executor=executor
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "READY")

    def test_segmented_exact_phrase_is_accepted(self):
        async def executor():
            return R1OAuthRefreshSnapshot(state="READY", reason="fixture")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                ["--confirm-code", *R1_OAUTH_REFRESH_CONFIRMATION.split()],
                executor=executor,
            )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
