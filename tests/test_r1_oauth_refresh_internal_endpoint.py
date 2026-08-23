import unittest
from datetime import datetime, timezone

from bitrix_connector.r1_oauth_refresh_execution_owner import (
    R1OAuthRefreshSnapshot,
    R1_OAUTH_REFRESH_CONFIRMATION,
)
from bitrix_connector.r1_oauth_refresh_internal_endpoint import (
    R1InternalInvocationPrincipal,
    authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once,
    build_r1_oauth_refresh_internal_endpoint_plan,
    invoke_injected_r1_oauth_refresh_internal_endpoint_once,
)
from bitrix_connector.r1_oauth_refresh_workload_identity_auth import (
    R1ValidatedWorkloadIdentity,
    build_r1_internal_workload_identity_policy,
    validate_r1_internal_workload_identity_once,
)


class R1OAuthRefreshInternalEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_is_inert_and_rejects_client_actor_surface(self):
        plan = build_r1_oauth_refresh_internal_endpoint_plan()
        self.assertEqual(plan.state, "LOCAL_READY")
        self.assertEqual(
            plan.authentication, "APPLICATION_VALIDATED_WORKLOAD_IDENTITY"
        )
        self.assertFalse(plan.client_actor_accepted)
        self.assertEqual(plan.route_mounts, 0)
        self.assertEqual(plan.deployment_calls, 0)
        self.assertEqual(plan.external_calls, 0)

    async def test_missing_server_principal_does_not_invoke_executor(self):
        calls = 0

        async def executor():
            nonlocal calls
            calls += 1
            return R1OAuthRefreshSnapshot(state="READY")

        snapshot = await invoke_injected_r1_oauth_refresh_internal_endpoint_once(
            build_r1_oauth_refresh_internal_endpoint_plan(),
            principal=None,
            confirmation=R1_OAUTH_REFRESH_CONFIRMATION,
            executor=executor,
        )
        self.assertEqual(snapshot.reason, "r1_internal_endpoint_rejected")
        self.assertEqual(calls, 0)

    async def test_server_principal_and_literal_delegate_once(self):
        calls = 0

        async def executor():
            nonlocal calls
            calls += 1
            return R1OAuthRefreshSnapshot(state="READY", reason="fixture")

        snapshot = await invoke_injected_r1_oauth_refresh_internal_endpoint_once(
            build_r1_oauth_refresh_internal_endpoint_plan(),
            principal=R1InternalInvocationPrincipal(
                subject="platform-fixture",
                authenticated_at=datetime.now(timezone.utc),
            ),
            confirmation=R1_OAUTH_REFRESH_CONFIRMATION,
            executor=executor,
        )
        self.assertEqual(snapshot.state, "READY")
        self.assertEqual(calls, 1)

    async def test_validated_workload_identity_delegates_once(self):
        calls = 0
        now = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)

        async def executor():
            nonlocal calls
            calls += 1
            return R1OAuthRefreshSnapshot(state="READY")

        snapshot = await authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once(
            build_r1_oauth_refresh_internal_endpoint_plan(),
            policy=build_r1_internal_workload_identity_policy(
                issuer="issuer-fixture",
                audience="audience-fixture",
                authorized_client_id="client-fixture",
            ),
            identity=R1ValidatedWorkloadIdentity(
                issuer="issuer-fixture",
                audience="audience-fixture",
                client_id="client-fixture",
                subject="workload-fixture",
                authenticated_at=now,
                expires_at=now.replace(minute=4),
            ),
            now=now,
            confirmation=R1_OAUTH_REFRESH_CONFIRMATION,
            executor=executor,
        )
        self.assertEqual(snapshot.state, "READY")
        self.assertEqual(calls, 1)

    async def test_wrong_workload_client_rejects_before_executor(self):
        calls = 0
        now = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)

        async def executor():
            nonlocal calls
            calls += 1
            return R1OAuthRefreshSnapshot(state="READY")

        snapshot = await authenticate_and_invoke_r1_oauth_refresh_internal_endpoint_once(
            build_r1_oauth_refresh_internal_endpoint_plan(),
            policy=build_r1_internal_workload_identity_policy(
                issuer="issuer-fixture",
                audience="audience-fixture",
                authorized_client_id="client-fixture",
            ),
            identity=R1ValidatedWorkloadIdentity(
                issuer="issuer-fixture",
                audience="audience-fixture",
                client_id="other-client",
                subject="workload-fixture",
                authenticated_at=now,
                expires_at=now.replace(minute=4),
            ),
            now=now,
            confirmation=R1_OAUTH_REFRESH_CONFIRMATION,
            executor=executor,
        )
        self.assertEqual(snapshot.reason, "r1_internal_identity_rejected")
        self.assertEqual(calls, 0)

    def test_stale_or_unverified_workload_identity_is_rejected(self):
        now = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        policy = build_r1_internal_workload_identity_policy(
            issuer="issuer-fixture",
            audience="audience-fixture",
            authorized_client_id="client-fixture",
        )
        stale = R1ValidatedWorkloadIdentity(
            issuer="issuer-fixture",
            audience="audience-fixture",
            client_id="client-fixture",
            subject="workload-fixture",
            authenticated_at=now.replace(minute=54, hour=11),
            expires_at=now.replace(minute=4),
        )
        self.assertFalse(
            validate_r1_internal_workload_identity_once(policy, stale, now=now)
        )
        unverified = R1ValidatedWorkloadIdentity(
            issuer="issuer-fixture",
            audience="audience-fixture",
            client_id="client-fixture",
            subject="workload-fixture",
            authenticated_at=now,
            expires_at=now.replace(minute=4),
            signature_validated=False,  # type: ignore[arg-type]
        )
        self.assertFalse(
            validate_r1_internal_workload_identity_once(
                policy, unverified, now=now
            )
        )


if __name__ == "__main__":
    unittest.main()
