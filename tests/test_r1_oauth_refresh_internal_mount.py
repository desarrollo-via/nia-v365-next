import unittest
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.r1_oauth_refresh_execution_owner import R1OAuthRefreshSnapshot
from bitrix_connector.r1_oauth_refresh_internal_endpoint import R1_OAUTH_REFRESH_INTERNAL_PATH
from bitrix_connector.r1_oauth_refresh_internal_mount import (
    mount_r1_oauth_refresh_internal_router,
)
from bitrix_connector.r1_oauth_refresh_internal_router import (
    R1OAuthRefreshInternalRouterBindings,
)
from bitrix_connector.r1_oauth_refresh_workload_identity_auth import (
    build_r1_internal_workload_identity_policy,
)


class R1OAuthRefreshInternalMountTests(unittest.TestCase):
    def setUp(self):
        self.calls = 0

        async def executor():
            self.calls += 1
            return R1OAuthRefreshSnapshot(state="READY")

        self.app = FastAPI()
        self.result = mount_r1_oauth_refresh_internal_router(
            self.app,
            bindings=R1OAuthRefreshInternalRouterBindings(
                policy=build_r1_internal_workload_identity_policy(
                    issuer="issuer-fixture",
                    audience="audience-fixture",
                    authorized_client_id="client-fixture",
                ),
                jwks_by_kid={},
                executor=executor,
                now_provider=lambda: datetime(2026, 8, 24, tzinfo=timezone.utc),
            ),
        )
        self.client = TestClient(self.app)

    def test_exact_route_rejects_anonymous_request_without_owner(self):
        response = self.client.post(R1_OAUTH_REFRESH_INTERNAL_PATH)
        self.assertTrue(self.result.mounted)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.calls, 0)

    def test_mount_is_idempotent(self):
        result = mount_r1_oauth_refresh_internal_router(
            self.app,
            bindings=R1OAuthRefreshInternalRouterBindings(
                policy=build_r1_internal_workload_identity_policy(
                    issuer="issuer-fixture",
                    audience="audience-fixture",
                    authorized_client_id="client-fixture",
                ),
                jwks_by_kid={},
                executor=lambda: None,  # type: ignore[arg-type]
            ),
        )
        self.assertFalse(result.mounted)
        self.assertEqual(result.reason, "already_mounted")


if __name__ == "__main__":
    unittest.main()
