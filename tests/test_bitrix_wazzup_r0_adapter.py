import ast
import unittest
from pathlib import Path

from bitrix_connector.wazzup_r0_adapter import (
    InMemoryWazzupR0Adapter,
    WazzupR0AdapterMountStatus,
    WazzupR0ObservationStatus,
    WazzupR0Scope,
    build_optional_wazzup_r0_adapter,
)


ROOT = Path(__file__).resolve().parents[1]
SWITCH = "NIA_WAZZUP_R0_ADAPTER_ENABLED"


def scope() -> WazzupR0Scope:
    return WazzupR0Scope(
        channel_id="synthetic-channel-001",
        chat_type="whatsapp",
        chat_id="573000000000",
    )


def message(*, message_id="synthetic-message-001", **overrides):
    data = {
        "messageId": message_id,
        "channelId": "synthetic-channel-001",
        "chatType": "whatsapp",
        "chatId": "573000000000",
        "dateTime": "2026-07-29T19:00:00.000Z",
        "type": "text",
        "status": "inbound",
        "text": "mensaje sintetico que no debe aparecer en recibos",
        "isEcho": False,
        "ignoredOfficialField": "compatible",
    }
    data.update(overrides)
    return data


def payload(**overrides):
    return {"messages": [message(**overrides)]}


class WazzupR0AdapterTests(unittest.TestCase):
    def test_switch_defaults_off_and_only_literal_true_builds(self):
        forbidden = lambda headers: (_ for _ in ()).throw(AssertionError())

        absent = build_optional_wazzup_r0_adapter({}, header_verifier=forbidden)
        false = build_optional_wazzup_r0_adapter(
            {SWITCH: "false"},
            header_verifier=forbidden,
        )
        invalid = build_optional_wazzup_r0_adapter(
            {SWITCH: "active"},
            scope=scope(),
            header_verifier=forbidden,
        )
        enabled = build_optional_wazzup_r0_adapter(
            {SWITCH: " TRUE "},
            scope=scope(),
            header_verifier=lambda headers: True,
        )

        self.assertEqual(absent.status, WazzupR0AdapterMountStatus.DISABLED)
        self.assertEqual(false.status, WazzupR0AdapterMountStatus.DISABLED)
        self.assertEqual(invalid.status, WazzupR0AdapterMountStatus.UNAVAILABLE)
        self.assertEqual(enabled.status, WazzupR0AdapterMountStatus.READY)
        self.assertIsNotNone(enabled.adapter)

    def test_enabled_without_scope_or_authentication_fails_closed(self):
        missing = build_optional_wazzup_r0_adapter({SWITCH: "true"})
        invalid_limit = build_optional_wazzup_r0_adapter(
            {SWITCH: "true"},
            scope=scope(),
            header_verifier=lambda headers: True,
            max_seen_events=0,
        )

        self.assertFalse(missing.enabled)
        self.assertEqual(
            missing.reason,
            "wazzup_r0_adapter_configuration_incomplete",
        )
        self.assertFalse(invalid_limit.enabled)
        self.assertEqual(
            invalid_limit.reason,
            "wazzup_r0_adapter_configuration_invalid",
        )

    def test_authentication_precedes_payload_validation(self):
        rejected = InMemoryWazzupR0Adapter(
            scope=scope(),
            header_verifier=lambda headers: False,
        ).observe({"messages": "invalid"}, headers={"Authorization": "hidden"})

        def unavailable(headers):
            raise RuntimeError("secret transport detail")

        failed = InMemoryWazzupR0Adapter(
            scope=scope(),
            header_verifier=unavailable,
        ).observe(payload(), headers={})

        self.assertEqual(rejected.status, WazzupR0ObservationStatus.REJECTED)
        self.assertEqual(rejected.reason, "wazzup_r0_unauthorized")
        self.assertEqual(failed.status, WazzupR0ObservationStatus.UNAVAILABLE)
        self.assertNotIn("secret transport detail", repr(failed))

    def test_exact_inbound_message_produces_only_inert_receipt(self):
        adapter = InMemoryWazzupR0Adapter(
            scope=scope(),
            header_verifier=lambda headers: headers.get("x-fixture") == "ok",
        )
        result = adapter.observe(payload(), headers={"x-fixture": "ok"})

        self.assertEqual(result.status, WazzupR0ObservationStatus.OBSERVED)
        self.assertEqual(result.reason, "connector_locked_off")
        self.assertTrue(result.identity_verified)
        self.assertEqual(result.text_length, 49)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_called)
        self.assertFalse(result.bitrix_written)
        self.assertNotIn("mensaje sintetico", repr(result))
        self.assertNotIn("mensaje sintetico", result.model_dump_json())

    def test_duplicate_is_bounded_and_never_persisted(self):
        adapter = InMemoryWazzupR0Adapter(
            scope=scope(),
            header_verifier=lambda headers: True,
            max_seen_events=1,
        )
        first = adapter.observe(payload(), headers={})
        duplicate = adapter.observe(payload(), headers={})
        second = adapter.observe(
            payload(message_id="synthetic-message-002"),
            headers={},
        )
        evicted = adapter.observe(payload(), headers={})

        self.assertEqual(first.status, WazzupR0ObservationStatus.OBSERVED)
        self.assertEqual(duplicate.status, WazzupR0ObservationStatus.DUPLICATE)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(second.status, WazzupR0ObservationStatus.OBSERVED)
        self.assertEqual(evicted.status, WazzupR0ObservationStatus.OBSERVED)
        self.assertFalse(duplicate.persisted)

    def test_non_inbound_and_other_wazzup_identity_are_ignored(self):
        adapter = InMemoryWazzupR0Adapter(
            scope=scope(),
            header_verifier=lambda headers: True,
        )
        outbound = adapter.observe(payload(status="sent"), headers={})
        echo = adapter.observe(payload(isEcho=True), headers={})
        other = adapter.observe(payload(chatId="573111111111"), headers={})

        self.assertEqual(outbound.reason, "wazzup_r0_not_inbound")
        self.assertEqual(echo.reason, "wazzup_r0_not_inbound")
        self.assertEqual(other.reason, "wazzup_r0_outside_scope")
        self.assertFalse(other.identity_verified)

    def test_invalid_or_batch_payload_never_reaches_observation(self):
        adapter = InMemoryWazzupR0Adapter(
            scope=scope(),
            header_verifier=lambda headers: True,
        )
        missing_content = payload()
        del missing_content["messages"][0]["text"]
        invalid = adapter.observe(missing_content, headers={})
        batch = adapter.observe(
            {"messages": [message(), message(message_id="synthetic-message-002")]},
            headers={},
        )

        self.assertEqual(invalid.status, WazzupR0ObservationStatus.INVALID)
        self.assertEqual(invalid.reason, "wazzup_r0_payload_invalid")
        self.assertEqual(batch.status, WazzupR0ObservationStatus.INVALID)
        self.assertEqual(batch.reason, "wazzup_r0_batch_unsupported")

    def test_adapter_is_not_mounted_and_has_no_external_runtime_imports(self):
        source_path = ROOT / "bitrix_connector" / "wazzup_r0_adapter.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        forbidden = {"fastapi", "httpx", "motor", "pymongo", "dotenv", "os"}
        self.assertTrue(forbidden.isdisjoint(imports))

        for relative in ("main.py", "bitrix_connector/router.py"):
            mounted_source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("wazzup_r0_adapter", mounted_source)
            self.assertNotIn(SWITCH, mounted_source)


if __name__ == "__main__":
    unittest.main()
