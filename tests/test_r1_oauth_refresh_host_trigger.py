import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.r1_oauth_refresh_host_trigger import (
    R1_OAUTH_REFRESH_HOST_TRIGGER_PATH,
    _managed_identity_scope,
    create_r1_oauth_refresh_host_trigger_router,
)
from bitrix_connector.r1_oauth_refresh_internal_router import (
    R1OAuthRefreshInternalRouterBindings,
)
from bitrix_connector.r1_oauth_refresh_workload_identity_auth import (
    build_r1_internal_workload_identity_policy,
)


class R1OAuthRefreshHostTriggerTests(unittest.TestCase):
    def test_managed_identity_uses_default_scope_without_changing_audience(self):
        self.assertEqual(
            _managed_identity_scope("api://audience-fixture"),
            "api://audience-fixture/.default",
        )
        self.assertEqual(
            _managed_identity_scope("api://audience-fixture/.default"),
            "api://audience-fixture/.default",
        )

    def test_anonymous_trigger_is_401_without_jwks_or_owner_activity(self):
        jwks_calls = 0

        def resolve_jwks():
            nonlocal jwks_calls
            jwks_calls += 1
            return {}

        async def executor():
            raise AssertionError("owner must not run")

        app = FastAPI()
        bindings = R1OAuthRefreshInternalRouterBindings(
            policy=build_r1_internal_workload_identity_policy(
                issuer="issuer-fixture",
                audience="audience-fixture",
                authorized_client_id="client-fixture",
            ),
            jwks_by_kid={},
            jwks_resolver=resolve_jwks,
            executor=executor,
        )
        app.include_router(
            create_r1_oauth_refresh_host_trigger_router(app, bindings=bindings)
        )
        response = TestClient(app).post(R1_OAUTH_REFRESH_HOST_TRIGGER_PATH)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(jwks_calls, 0)


if __name__ == "__main__":
    unittest.main()
