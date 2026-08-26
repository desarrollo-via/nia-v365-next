import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bitrix_connector.r1_post_write_close_host_executor import (
    ExactManagedIdentityPostWriteControl,
    HostCloseState,
    PersistentHostCloseStore,
    R1PostWritePersistentHostExecutor,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES,
    SWITCH_ORDER,
)


def checkpoint(path: Path) -> None:
    path.write_text(json.dumps({
        "write_budget": 1,
        "write_reserved": 0,
        "write_succeeded": 1,
        "write_used": 1,
    }), encoding="utf-8")


class FakeControl:
    def __init__(self, calls): self.calls = calls
    async def preflight_once(self):
        self.calls.append("preflight"); return True
    async def close_writer_once(self):
        self.calls.append("key_vault"); return True
    async def restore_switches_and_restart_once(self):
        self.calls.append("restore_restart")
    async def verify_closed_once(self):
        self.calls.append("verify"); return True
    async def close(self): self.calls.append("close")


class HostExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistent_restart_phase_never_repeats_effects(self):
        calls = []
        async def session(): calls.append("session"); return True
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.json"
            checkpoint(ledger)
            store = PersistentHostCloseStore(path=root / "state.json")
            executor = R1PostWritePersistentHostExecutor(
                checkpoint_path=ledger,
                store=store,
                session_close=session,
                control_factory=lambda: FakeControl(calls),
            )
            first = await executor()
            self.assertEqual(first.state, "NO-GO-REMAINDER")
            self.assertEqual(first.failure_surface, "restart_pending")
            self.assertEqual(store.read().phase, "RESTART-REQUESTED")
            second = await executor()
            self.assertEqual(second.state, "VERIFIED-RESTORED")
            self.assertEqual(store.read().phase, "VERIFIED")
        self.assertEqual(calls, [
            "preflight", "session", "key_vault", "restore_restart", "close",
            "verify", "close",
        ])

    async def test_invalid_checkpoint_has_zero_factories_or_effects(self):
        calls = []
        async def session(): calls.append("session"); return True
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.json"
            ledger.write_text("{}", encoding="utf-8")
            executor = R1PostWritePersistentHostExecutor(
                checkpoint_path=ledger,
                store=PersistentHostCloseStore(path=root / "state.json"),
                session_close=session,
                control_factory=lambda: calls.append("control"),
            )
            result = await executor()
        self.assertEqual(result.failure_surface, "checkpoint")
        self.assertEqual(calls, [])

    def test_corrupt_persistent_state_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"phase":"CLAIMED","extra":1}', encoding="utf-8")
            self.assertEqual(
                PersistentHostCloseStore(path=path).read(),
                HostCloseState("NO-GO"),
            )


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.content = json.dumps(self._payload).encode()
    def json(self): return self._payload


class Credential:
    async def get_token(self, scope):
        return type("Token", (), {"token": "fixture-token"})()
    async def close(self): pass


class Http:
    def __init__(self): self.calls = []
    async def request(self, method, url, headers=None, json=None):
        self.calls.append((method, url, json))
        if method == "POST" and "/config/appsettings/list?" in url:
            return Response(200, {"properties": {
                "UNRELATED": "preserved",
                **{name: "active" for name in SWITCH_ORDER},
            }})
        if method == "PUT": return Response(200)
        if method == "POST" and "/restart?" in url: return Response(204)
        raise AssertionError((method, url))
    async def aclose(self): pass


class ArmPreservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_preserves_unrelated_values_in_memory(self):
        http = Http()
        control = ExactManagedIdentityPostWriteControl(
            credential=Credential(), http_client=http
        )
        await control.restore_switches_and_restart_once()
        put = next(call for call in http.calls if call[0] == "PUT")
        properties = put[2]["properties"]
        self.assertEqual(properties["UNRELATED"], "preserved")
        self.assertEqual(
            {name: properties[name] for name in SWITCH_ORDER},
            EXPECTED_BASELINE_VALUES,
        )
        self.assertEqual([call[0] for call in http.calls], [
            "POST", "PUT", "POST",
        ])


if __name__ == "__main__":
    unittest.main()
