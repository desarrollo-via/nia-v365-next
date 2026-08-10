import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.bitrix_event_scoped_r1_mount import (
    build_optional_event_scoped_r1_mount,
    build_dormant_event_scoped_r1_mount,
    mount_optional_event_scoped_r1_fail_isolated,
)
from bitrix_connector.bitrix_event_scoped_r1_gate import EventScopedR1Gate
from bitrix_connector.bitrix_event_scoped_r1_gate import (
    EVENT_R1_FIRST_CONFIRMATION,
)
from bitrix_connector.config import load_settings
from bitrix_connector.event_scoped_oauth import BOT_EVENT_ACCESS_TOKEN_KEY
import bitrix_connector.router as connector_router_module


def form():
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "373259",
        "data[bot][code]": "nia_next_openline_controlled",
        BOT_EVENT_ACCESS_TOKEN_KEY: "fixture-private-event-token",
        "data[message][id]": "9001",
        "data[message][chatId]": "78733",
        "data[message][authorId]": "27",
        "data[message][text]": "fixture controlled",
        "data[message][isSystem]": "0",
        "data[chat][dialogId]": "chat78733",
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "data[user][bot]": "0",
        "data[user][connector]": "1",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": "member-controlled",
        "auth[application_token]": "application-secret",
    }


class EventScopedR1MountTests(unittest.TestCase):
    @staticmethod
    def enabled_settings(**overrides):
        values = {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_EVENT_R1_ENABLED": "true",
            "NIA_BASE_URL": "https://nia.test",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-controlled",
            "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
            "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-1234567890",
            "NIA_BITRIX_REVIEW_ACTOR": "reviewer",
            "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "credential-fixture",
        }
        values.update(overrides)
        return load_settings(values)

    @staticmethod
    def fake_gate():
        async def inert(*_args):
            raise AssertionError("not called while only mounting")

        return EventScopedR1Gate(
            preflight=inert,
            roundtrip=inert,
            execution_enabled=True,
        )

    def test_default_mount_is_dormant_and_has_no_activation_surface(self):
        mount = build_dormant_event_scoped_r1_mount()
        self.assertEqual(mount.state, "DORMANT")
        self.assertFalse(mount.requested)
        self.assertFalse(mount.enabled)
        self.assertIsNone(mount.observer)
        self.assertFalse(mount.activation_surface_available)
        self.assertEqual((mount.nia_calls, mount.bitrix_calls), (0, 0))

    def test_any_activation_attempt_fails_closed_without_observer(self):
        async def observer(*_args):
            raise AssertionError("must never be reachable")

        for kwargs in ({"requested": True}, {"observer": observer}):
            with self.subTest(kwargs=tuple(kwargs)):
                mount = build_dormant_event_scoped_r1_mount(**kwargs)
                self.assertEqual(mount.state, "UNAVAILABLE")
                self.assertFalse(mount.enabled)
                self.assertIsNone(mount.observer)
                self.assertFalse(mount.execution_enabled)

    def test_explicit_safe_switch_mounts_one_owner_and_protected_surface(self):
        mount = build_optional_event_scoped_r1_mount(
            self.enabled_settings(),
            gate_factory=self.fake_gate,
        )
        self.assertEqual(mount.state, "MOUNTED")
        self.assertTrue(mount.requested)
        self.assertTrue(mount.enabled)
        self.assertTrue(mount.observer_bound)
        self.assertTrue(mount.activation_surface_available)
        self.assertTrue(mount.execution_enabled)
        self.assertFalse(mount.participant_roundtrip_bound)
        self.assertFalse(mount.pre_event_lease_factory_bound)
        self.assertEqual(mount.participant_strategy, "none")
        self.assertEqual(mount.participant_mount_count, 0)
        self.assertIsNotNone(mount.router)
        self.assertIsNotNone(mount.owner)
        self.assertIsNotNone(mount.observer)

    def test_production_composition_can_arm_without_calling_external_dependencies(self):
        mount = build_optional_event_scoped_r1_mount(self.enabled_settings())
        self.assertTrue(mount.participant_roundtrip_bound)
        self.assertFalse(mount.pre_event_lease_factory_bound)
        self.assertEqual(mount.participant_strategy, "posterior")
        self.assertEqual(mount.participant_mount_count, 1)
        app = FastAPI()
        app.include_router(mount.router)
        with TestClient(app) as client:
            first = client.post(
                "/internal/r1-event/first-confirmation",
                headers={
                    "Authorization": "Bearer review-token-fixture-1234567890"
                },
                json={"confirmation": EVENT_R1_FIRST_CONFIRMATION},
            )
            disarmed = client.delete(
                "/internal/r1-event/session",
                headers={
                    "Authorization": "Bearer review-token-fixture-1234567890"
                },
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["state"], "AWAITING-MANUAL-REMOVAL")
        self.assertEqual(first.json()["preflight_calls"], 0)
        self.assertEqual(first.json()["roundtrip_calls"], 0)
        self.assertEqual(disarmed.json()["state"], "DISARMED")

    def test_pre_event_strategy_excludes_posterior_wrapper(self):
        mount = build_optional_event_scoped_r1_mount(
            self.enabled_settings(),
            pre_event_lease_factory=lambda: None,
        )

        self.assertTrue(mount.pre_event_lease_factory_bound)
        self.assertFalse(mount.participant_roundtrip_bound)
        self.assertEqual(mount.participant_strategy, "pre-event")
        self.assertEqual(mount.participant_mount_count, 1)

    def test_ambiguous_participant_strategies_fail_isolated(self):
        parent = FastAPI()
        mount = mount_optional_event_scoped_r1_fail_isolated(
            parent.router,
            self.enabled_settings(),
            gate_factory=self.fake_gate,
            pre_event_lease_factory=lambda: None,
        )

        self.assertEqual(mount.state, "UNAVAILABLE")
        self.assertEqual(
            mount.reason, "event_r1_participant_strategy_ambiguous"
        )
        self.assertEqual(mount.participant_mount_count, 0)

    def test_integrated_default_router_exposes_no_r1_control_routes(self):
        paths = {route.path for route in connector_router_module.router.routes}
        self.assertNotIn(
            "/bitrix-connector/internal/r1-event/status",
            paths,
        )

    def test_missing_auth_or_parallel_r0_bridge_fails_isolated(self):
        cases = (
            (
                self.enabled_settings(NIA_BITRIX_REVIEW_TOKEN=""),
                "event_r1_review_auth_missing",
            ),
            (
                self.enabled_settings(NIA_BITRIX_R0_BRIDGE_ENABLED="true"),
                "event_r1_safety_state_invalid",
            ),
        )
        for settings, reason in cases:
            with self.subTest(reason=reason):
                parent = FastAPI()
                mount = mount_optional_event_scoped_r1_fail_isolated(
                    parent.router,
                    settings,
                    gate_factory=self.fake_gate,
                )
                self.assertEqual(mount.state, "UNAVAILABLE")
                self.assertFalse(mount.enabled)
                self.assertIsNone(mount.observer)
                self.assertEqual(mount.reason, reason)

    def test_invalid_switch_is_unavailable_and_default_remains_dormant(self):
        parent = FastAPI()
        invalid = mount_optional_event_scoped_r1_fail_isolated(
            parent.router,
            load_settings({"NIA_BITRIX_EVENT_R1_ENABLED": "maybe"}),
            gate_factory=self.fake_gate,
        )
        default = build_optional_event_scoped_r1_mount(load_settings({}))
        self.assertEqual(invalid.state, "UNAVAILABLE")
        self.assertEqual(invalid.reason, "event_r1_switch_invalid")
        self.assertEqual(default.state, "DORMANT")
        self.assertFalse(default.activation_surface_available)

    def test_integrated_webhook_remains_inert_with_private_token_present(self):
        mount = build_dormant_event_scoped_r1_mount()
        app = FastAPI()
        app.include_router(connector_router_module.router)
        environ = {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-controlled",
            "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        }
        with patch.object(
            connector_router_module,
            "event_scoped_r1_mount",
            mount,
        ), patch.dict(os.environ, environ, clear=True):
            with TestClient(app) as client:
                response = client.post(
                    "/bitrix-connector/webhook",
                    data=form(),
                )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["reason"], "connector_locked_off")
        self.assertFalse(payload["persisted"])
        self.assertFalse(payload["nia_called"])
        self.assertFalse(payload["bitrix_written"])
        self.assertNotIn("fixture-private-event-token", response.text)


if __name__ == "__main__":
    unittest.main()
