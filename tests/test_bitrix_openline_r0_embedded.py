import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from bitrix_connector.config import load_settings
from bitrix_connector.openline_r0_bridge import InMemoryR0ReceiptBridge
from bitrix_connector.openline_r0_bridge_mount import (
    R0BridgeMount,
    R0BridgeMountConfigurationError,
    R0_BRIDGE_EMBEDDED_PREFIX,
    build_optional_r0_bridge_mount,
    mount_optional_r0_bridge_fail_isolated,
)
import bitrix_connector.router as connector_router_module
import bitrix_connector.openline_r0_bridge_mount as bridge_mount_module


TOKEN = "review-token-controlado-123456789"


def bridge_settings(**changes):
    values = {
        "NIA_BITRIX_MODE": "off",
        "NIA_BITRIX_R0_BRIDGE_ENABLED": "true",
        "NIA_BITRIX_REVIEW_TOKEN": TOKEN,
        "NIA_BITRIX_REVIEW_ACTOR": "hugo",
        "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "reviewer:hugo:r0",
    }
    values.update(changes)
    return load_settings(values)


def webhook_form():
    return {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "373259",
        "data[message][id]": "9100",
        "data[message][chatId]": "78733",
        "data[message][authorId]": "27",
        "data[message][text]": "mensaje controlado",
        "data[chat][dialogId]": "chat78733",
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "auth[domain]": "portal.bitrix24.test",
        "auth[member_id]": "member-controlled",
        "auth[application_token]": "application-secret",
    }


class EmbeddedR0BridgeMountTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def base_connector_router() -> APIRouter:
        parent = APIRouter(prefix="/bitrix-connector")

        async def endpoint():
            return {"status": "ok"}

        for index in range(14):
            parent.add_api_route(
                f"/base-{index}",
                endpoint,
                methods=["GET"],
                name=f"base_{index}",
            )
        return parent

    @staticmethod
    def route_counts(parent: APIRouter) -> tuple[int, int, int]:
        app = FastAPI()
        app.include_router(parent)
        paths = tuple(app.openapi()["paths"])
        bitrix_paths = tuple(
            path for path in paths if path.startswith("/bitrix-connector")
        )
        r0_paths = tuple(
            path
            for path in paths
            if path.startswith(
                "/bitrix-connector/internal/r0-receipts"
            )
        )
        return len(paths) + 4, len(bitrix_paths), len(r0_paths)

    def test_default_keeps_embedded_router_without_r0_routes(self):
        mount = build_optional_r0_bridge_mount(
            load_settings({}),
            prefix=R0_BRIDGE_EMBEDDED_PREFIX,
        )

        self.assertFalse(mount.enabled)
        self.assertIsNone(mount.router)
        self.assertIsNone(mount.receipt_observer)

    def test_exact_switch_adds_three_paths_and_four_operations_once(self):
        bridge = InMemoryR0ReceiptBridge()
        mount = build_optional_r0_bridge_mount(
            bridge_settings(),
            prefix=R0_BRIDGE_EMBEDDED_PREFIX,
            bridge_factory=lambda: bridge,
        )
        parent = APIRouter(prefix="/bitrix-connector")
        parent.include_router(mount.router)

        operations = {
            (route.path, method)
            for route in parent.routes
            for method in route.methods
        }
        self.assertEqual(
            operations,
            {
                (
                    "/bitrix-connector/internal/r0-receipts/arm",
                    "POST",
                ),
                (
                    "/bitrix-connector/internal/r0-receipts/{run_id}",
                    "GET",
                ),
                (
                    "/bitrix-connector/internal/r0-receipts/{run_id}/consume",
                    "POST",
                ),
                (
                    "/bitrix-connector/internal/r0-receipts/{run_id}",
                    "DELETE",
                ),
            },
        )
        self.assertIs(mount.receipt_observer.__self__, bridge)

    def test_requested_bridge_with_incomplete_auth_fails_closed(self):
        with self.assertRaisesRegex(
            R0BridgeMountConfigurationError,
            "r0_bridge_review_auth_missing",
        ):
            build_optional_r0_bridge_mount(
                bridge_settings(NIA_BITRIX_REVIEW_TOKEN=""),
                prefix=R0_BRIDGE_EMBEDDED_PREFIX,
            )

    def test_requested_active_mode_blocks_bridge_despite_effective_off(self):
        with self.assertRaisesRegex(
            R0BridgeMountConfigurationError,
            "r0_bridge_safety_state_invalid",
        ):
            build_optional_r0_bridge_mount(
                bridge_settings(NIA_BITRIX_MODE="active"),
                prefix=R0_BRIDGE_EMBEDDED_PREFIX,
            )

    def test_invalid_r0_configuration_preserves_18_14_0(self):
        parent = self.base_connector_router()
        mount = mount_optional_r0_bridge_fail_isolated(
            parent,
            bridge_settings(NIA_BITRIX_REVIEW_TOKEN="short"),
            prefix=R0_BRIDGE_EMBEDDED_PREFIX,
        )

        self.assertFalse(mount.enabled)
        self.assertTrue(mount.requested)
        self.assertEqual(mount.status, "unavailable")
        self.assertEqual(mount.reason, "r0_bridge_review_auth_missing")
        self.assertEqual(self.route_counts(parent), (18, 14, 0))

    def test_valid_r0_configuration_composes_21_17_3(self):
        parent = self.base_connector_router()
        mount = mount_optional_r0_bridge_fail_isolated(
            parent,
            bridge_settings(),
            prefix=R0_BRIDGE_EMBEDDED_PREFIX,
        )

        self.assertTrue(mount.enabled)
        self.assertTrue(mount.requested)
        self.assertEqual(mount.status, "mounted")
        self.assertEqual(mount.reason, "r0_bridge_mounted")
        self.assertEqual(self.route_counts(parent), (21, 17, 3))

    def test_unknown_configuration_detail_is_not_exposed(self):
        parent = self.base_connector_router()
        with patch.object(
            bridge_mount_module,
            "build_optional_r0_bridge_mount",
            side_effect=R0BridgeMountConfigurationError(
                "protected-value-must-not-leak"
            ),
        ):
            mount = mount_optional_r0_bridge_fail_isolated(
                parent,
                bridge_settings(),
                prefix=R0_BRIDGE_EMBEDDED_PREFIX,
            )

        self.assertEqual(mount.status, "unavailable")
        self.assertEqual(mount.reason, "r0_bridge_configuration_invalid")
        self.assertNotIn("protected-value", repr(mount))
        self.assertEqual(self.route_counts(parent), (18, 14, 0))

    async def test_health_exposes_only_safe_unavailable_state(self):
        mount = R0BridgeMount(
            enabled=False,
            requested=True,
            status="unavailable",
            reason="r0_bridge_review_auth_missing",
        )

        with patch.object(
            connector_router_module,
            "embedded_r0_bridge_mount",
            mount,
        ):
            health = await connector_router_module.connector_health()

        self.assertEqual(
            health.r0_bridge,
            {
                "requested": True,
                "mounted": False,
                "status": "unavailable",
                "reason": "r0_bridge_review_auth_missing",
            },
        )
        self.assertNotIn(TOKEN, health.model_dump_json())

    async def test_integrated_webhook_uses_composed_observer(self):
        observer = AsyncMock()
        mount = R0BridgeMount(
            enabled=True,
            receipt_observer=observer,
            requested=True,
            status="mounted",
            reason="r0_bridge_mounted",
        )
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
            "embedded_r0_bridge_mount",
            mount,
        ), patch.dict(os.environ, environ, clear=True):
            with TestClient(app) as client:
                response = client.post(
                    "/bitrix-connector/webhook",
                    data=webhook_form(),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "connector_locked_off")
        observer.assert_awaited_once()
        _, receipt, settings = observer.await_args.args
        self.assertFalse(receipt.persisted)
        self.assertFalse(receipt.nia_called)
        self.assertFalse(receipt.bitrix_written)
        self.assertEqual(settings.effective_mode.value, "off")


if __name__ == "__main__":
    unittest.main()
