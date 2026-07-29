import asyncio
import json
import unittest
from pathlib import Path

from bitrix_connector.wazzup_r0_adapter import WazzupR0Scope
from bitrix_connector.wazzup_r0_ingress import (
    WAZZUP_R0_INGRESS_PATH,
    WazzupR0IngressLimits,
    build_optional_wazzup_r0_ingress,
)


ROOT = Path(__file__).resolve().parents[1]
SWITCH = "NIA_WAZZUP_R0_ADAPTER_ENABLED"


def exact_scope():
    return WazzupR0Scope(
        channel_id="synthetic-channel-001",
        chat_type="whatsapp",
        chat_id="573000000000",
    )


def payload(message_id="synthetic-message-001"):
    return {
        "messages": [
            {
                "messageId": message_id,
                "channelId": "synthetic-channel-001",
                "chatType": "whatsapp",
                "chatId": "573000000000",
                "dateTime": "2026-07-29T19:00:00.000Z",
                "type": "text",
                "status": "inbound",
                "text": "contenido sintetico confidencial",
                "isEcho": False,
            }
        ]
    }


async def invoke(app, *, body=b"", headers=(), receive=None, method="POST", path=None):
    messages = []
    delivered = False

    async def default_receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path or WAZZUP_R0_INGRESS_PATH,
            "headers": list(headers),
        },
        receive or default_receive,
        send,
    )
    start = next(item for item in messages if item["type"] == "http.response.start")
    raw_body = b"".join(
        item.get("body", b"")
        for item in messages
        if item["type"] == "http.response.body"
    )
    return start, json.loads(raw_body)


class WazzupR0IngressTests(unittest.IsolatedAsyncioTestCase):
    def build(self, *, verifier=None, limits=None):
        verifier = verifier or (lambda headers: headers.get("x-fixture") == "ok")
        mount = build_optional_wazzup_r0_ingress(
            {SWITCH: "true"},
            scope=exact_scope(),
            header_verifier=verifier,
            **({"limits": limits} if limits is not None else {}),
        )
        self.assertTrue(mount.enabled)
        self.assertIsNotNone(mount.app)
        return mount.app

    async def test_authentication_happens_before_receive(self):
        touched = False

        async def forbidden_receive():
            nonlocal touched
            touched = True
            raise AssertionError("body must not be read")

        start, result = await invoke(
            self.build(verifier=lambda headers: False),
            headers=((b"authorization", b"hidden"),),
            receive=forbidden_receive,
        )

        self.assertEqual(start["status"], 401)
        self.assertEqual(result["reason"], "wazzup_r0_unauthorized")
        self.assertFalse(touched)
        self.assertNotIn("hidden", repr(result))

    async def test_exact_message_returns_inert_safe_receipt(self):
        body = json.dumps(payload()).encode("utf-8")
        start, result = await invoke(
            self.build(),
            body=body,
            headers=(
                (b"x-fixture", b"ok"),
                (b"content-length", str(len(body)).encode("ascii")),
            ),
        )

        self.assertEqual(start["status"], 200)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["reason"], "connector_locked_off")
        self.assertTrue(result["identity_verified"])
        self.assertFalse(result["persisted"])
        self.assertFalse(result["nia_called"])
        self.assertFalse(result["bitrix_written"])
        self.assertNotIn("contenido sintetico", repr(result))
        response_headers = dict(start["headers"])
        self.assertEqual(response_headers[b"cache-control"], b"no-store")
        self.assertEqual(response_headers[b"x-content-type-options"], b"nosniff")

    async def test_declared_and_streamed_oversize_are_rejected(self):
        limits = WazzupR0IngressLimits(max_body_bytes=16)
        app = self.build(limits=limits)
        declared, declared_result = await invoke(
            app,
            headers=((b"x-fixture", b"ok"), (b"content-length", b"17")),
        )
        chunks = iter(
            (
                {"type": "http.request", "body": b"x" * 10, "more_body": True},
                {"type": "http.request", "body": b"y" * 10, "more_body": False},
            )
        )

        async def streamed_receive():
            return next(chunks)

        streamed, streamed_result = await invoke(
            app,
            headers=((b"x-fixture", b"ok"),),
            receive=streamed_receive,
        )

        self.assertEqual(declared["status"], 413)
        self.assertEqual(streamed["status"], 413)
        self.assertEqual(declared_result["reason"], "wazzup_r0_body_too_large")
        self.assertEqual(streamed_result["reason"], "wazzup_r0_body_too_large")

    async def test_timeout_cancels_body_read(self):
        cancelled = asyncio.Event()

        async def blocked_receive():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        start, result = await invoke(
            self.build(
                limits=WazzupR0IngressLimits(request_timeout_seconds=0.01)
            ),
            headers=((b"x-fixture", b"ok"),),
            receive=blocked_receive,
        )

        self.assertEqual(start["status"], 504)
        self.assertEqual(result["reason"], "wazzup_r0_request_timeout")
        self.assertTrue(cancelled.is_set())

    async def test_duplicate_headers_and_json_keys_fail_closed(self):
        duplicate_headers, header_result = await invoke(
            self.build(),
            headers=((b"x-fixture", b"ok"), (b"x-fixture", b"ok")),
        )
        duplicate_json, json_result = await invoke(
            self.build(),
            body=b'{"messages":[],"messages":[]}',
            headers=((b"x-fixture", b"ok"),),
        )

        self.assertEqual(duplicate_headers["status"], 400)
        self.assertEqual(header_result["reason"], "wazzup_r0_headers_invalid")
        self.assertEqual(duplicate_json["status"], 422)
        self.assertEqual(json_result["reason"], "wazzup_r0_payload_invalid")

    async def test_non_finite_json_constants_fail_closed(self):
        app = self.build()
        valid_prefix = json.dumps(payload())[:-1]

        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                body = f'{valid_prefix},"ignored":{constant}}}'.encode("utf-8")
                start, result = await invoke(
                    app,
                    body=body,
                    headers=((b"x-fixture", b"ok"),),
                )

                self.assertEqual(start["status"], 422)
                self.assertEqual(result["reason"], "wazzup_r0_payload_invalid")
                self.assertFalse(result["persisted"])
                self.assertFalse(result["nia_called"])
                self.assertFalse(result["bitrix_written"])

    async def test_wrong_path_and_method_are_fixed_safe_responses(self):
        app = self.build()
        absent, absent_result = await invoke(app, path="/other")
        method, method_result = await invoke(app, method="GET")

        self.assertEqual(absent["status"], 404)
        self.assertEqual(absent_result["reason"], "wazzup_r0_route_not_found")
        self.assertEqual(method["status"], 405)
        self.assertEqual(method_result["reason"], "wazzup_r0_method_not_allowed")


class WazzupR0IngressCompositionTests(unittest.TestCase):
    def test_switch_absent_or_false_returns_no_asgi_app(self):
        forbidden = lambda headers: (_ for _ in ()).throw(AssertionError())
        for environ in ({}, {SWITCH: "false"}):
            with self.subTest(environ=environ):
                mount = build_optional_wazzup_r0_ingress(
                    environ,
                    scope=exact_scope(),
                    header_verifier=forbidden,
                )
                self.assertFalse(mount.enabled)
                self.assertIsNone(mount.app)

    def test_limits_reject_unsafe_values(self):
        for values in (
            {"max_body_bytes": 0},
            {"max_body_bytes": 1_048_577},
            {"max_body_chunks": 0},
            {"max_body_chunks": 1_025},
            {"request_timeout_seconds": 0},
            {"request_timeout_seconds": 31},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                WazzupR0IngressLimits(**values)

    def test_ingress_is_not_mounted_in_productive_surfaces(self):
        for relative in (
            "main.py",
            "bitrix_connector/router.py",
            "bitrix_connector/workflow_policy.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("wazzup_r0_ingress", source)
            self.assertNotIn(WAZZUP_R0_INGRESS_PATH, source)


if __name__ == "__main__":
    unittest.main()
