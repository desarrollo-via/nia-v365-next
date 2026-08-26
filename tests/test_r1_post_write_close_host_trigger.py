import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.r1_oauth_refresh_internal_router import (
    R1OAuthRefreshInternalRouterBindings,
)
from bitrix_connector.r1_oauth_refresh_workload_identity_auth import (
    build_r1_internal_workload_identity_policy,
)
from bitrix_connector.r1_post_write_close_host_trigger import (
    R1_POST_WRITE_CLOSE_TRIGGER_PATH,
    create_r1_post_write_close_host_trigger_router,
)
from bitrix_connector.r1_post_write_close_recovery import PostWriteCloseResult


class R1PostWriteCloseHostTriggerTests(unittest.TestCase):
    def build(self):
        calls = {"jwks": 0, "executor": 0}

        async def executor():
            calls["executor"] += 1
            return PostWriteCloseResult(
                state="NO-GO-REMAINDER",
                checkpoint_verified=True,
                session_closed=True,
                activation_closed=False,
                key_vault_closed=True,
                closure_attempts=3,
                failure_surface="activation",
                resources_closed=True,
            )

        bindings = R1OAuthRefreshInternalRouterBindings(
            policy=build_r1_internal_workload_identity_policy(
                issuer="issuer-fixture",
                audience="audience-fixture",
                authorized_client_id="client-fixture",
            ),
            jwks_by_kid={},
            executor=lambda: None,  # unrelated OAuth executor remains unused
        )
        app = FastAPI()
        app.include_router(create_r1_post_write_close_host_trigger_router(
            auth_bindings=bindings,
            executor=executor,
        ))
        return TestClient(app), calls

    def test_anonymous_is_401_before_jwks_or_recovery(self):
        client, calls = self.build()
        response = client.post(R1_POST_WRITE_CLOSE_TRIGGER_PATH)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(calls, {"jwks": 0, "executor": 0})

    def test_invalid_bearer_is_401_before_recovery(self):
        client, calls = self.build()
        response = client.post(
            R1_POST_WRITE_CLOSE_TRIGGER_PATH,
            headers={"Authorization": "Bearer invalid"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(calls, {"jwks": 0, "executor": 0})

    def test_valid_identity_consumes_exactly_one_attempt(self):
        client, calls = self.build()
        target = (
            "bitrix_connector.r1_post_write_close_host_trigger."
            "verify_r1_workload_identity_jwt_once"
        )
        with patch(target, return_value=object()):
            first = client.post(
                R1_POST_WRITE_CLOSE_TRIGGER_PATH,
                headers={"Authorization": "Bearer fixture"},
            )
            second = client.post(
                R1_POST_WRITE_CLOSE_TRIGGER_PATH,
                headers={"Authorization": "Bearer fixture"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["state"], "NO-GO-REMAINDER")
        self.assertEqual(first.json()["messages_sent"], 0)
        self.assertEqual(first.json()["secret_write_calls"], 0)
        self.assertEqual(first.json()["resume_calls"], 0)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(calls, {"jwks": 0, "executor": 1})


if __name__ == "__main__":
    unittest.main()
