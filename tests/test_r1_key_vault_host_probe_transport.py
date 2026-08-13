import json
import unittest
from pathlib import Path

from bitrix_connector.r1_key_vault_host_probe_transport import (
    DOUBLE_AUTHORIZATION,
    FixtureOnlyHostProbeTransportOwner,
    ProbeProcessResult,
)


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = (ROOT / "scripts" / "r1_key_vault_host_probe_payload.py").read_bytes()


def output(*, present=False, valid=None, extra=None):
    value = {
        "schema": "nia-next-r1-host-probe-v1",
        "packages": {
            "azure-identity": "1.25.3",
            "azure-keyvault-secrets": "4.11.0",
            "aiohttp": "3.14.3",
        },
        "setting_present": present,
        "setting_valid": valid,
        "external_calls": 0,
        "writes": 0,
    }
    if extra:
        value.update(extra)
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class TunnelDouble:
    kind = "fixture-double"

    def __init__(self, *, port=43210, fail=False, close_fail=False):
        self.port = port
        self.fail = fail
        self.close_fail = close_fail
        self.opens = []
        self.closes = 0

    def open_exact(self, **scope):
        self.opens.append(scope)
        if self.fail:
            raise RuntimeError("fixture_tunnel_failure")
        return self.port

    def close(self):
        self.closes += 1
        if self.close_fail:
            raise RuntimeError("fixture_tunnel_close_failure")


class ProcessDouble:
    kind = "fixture-double"

    def __init__(self, result=None, *, fail=False, close_fail=False):
        self.result = result or ProbeProcessResult(0, output(), b"")
        self.fail = fail
        self.close_fail = close_fail
        self.runs = []
        self.closes = 0

    def run_exact(self, **request):
        self.runs.append(request)
        if self.fail:
            raise RuntimeError("fixture_process_failure")
        return self.result

    def close(self):
        self.closes += 1
        if self.close_fail:
            raise RuntimeError("fixture_process_close_failure")


class R1HostProbeTransportTests(unittest.TestCase):
    def owner(self, tunnel=None, process=None):
        return FixtureOnlyHostProbeTransportOwner(
            payload=PAYLOAD,
            tunnel=tunnel or TunnelDouble(),
            process=process or ProcessDouble(),
        )

    def test_absent_baseline_uses_exact_scope_stdin_and_closes(self):
        tunnel, process = TunnelDouble(), ProcessDouble()
        result = self.owner(tunnel, process).run_once(DOUBLE_AUTHORIZATION)

        self.assertFalse(result.setting_present)
        self.assertIsNone(result.setting_valid)
        self.assertEqual(result.tunnel_opens, 1)
        self.assertEqual(result.process_runs, 1)
        self.assertEqual(result.retries, 0)
        self.assertTrue(result.closed)
        self.assertEqual(
            tunnel.opens,
            [{
                "subscription_id": "0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9",
                "resource_group": "nia-v365-next-api_group",
                "app_name": "nia-v365-next-api",
                "slot": "Production",
                "timeout_seconds": 30,
            }],
        )
        self.assertEqual(process.runs[0]["host"], "127.0.0.1")
        self.assertEqual(process.runs[0]["argv"], ("python", "-"))
        self.assertEqual(process.runs[0]["stdin"], PAYLOAD.replace(b"\r\n", b"\n"))
        self.assertEqual(process.runs[0]["timeout_seconds"], 15)
        self.assertEqual((process.closes, tunnel.closes), (1, 1))

    def test_present_valid_baseline_is_accepted_without_value(self):
        process = ProcessDouble(ProbeProcessResult(0, output(present=True, valid=True), b""))
        result = self.owner(process=process).run_once(DOUBLE_AUTHORIZATION)

        self.assertTrue(result.setting_present)
        self.assertTrue(result.setting_valid)
        self.assertFalse(hasattr(result, "setting_value"))

    def test_wrong_authorization_consumes_owner_without_opening(self):
        tunnel, process = TunnelDouble(), ProcessDouble()
        owner = self.owner(tunnel, process)

        with self.assertRaisesRegex(RuntimeError, "auth_invalid"):
            owner.run_once(DOUBLE_AUTHORIZATION + " ")
        with self.assertRaisesRegex(RuntimeError, "reuse_or_auth_invalid"):
            owner.run_once(DOUBLE_AUTHORIZATION)

        self.assertEqual(tunnel.opens, [])
        self.assertEqual(process.runs, [])

    def test_non_double_dependencies_are_rejected(self):
        tunnel = TunnelDouble()
        tunnel.kind = "production"
        with self.assertRaisesRegex(TypeError, "tunnel_not_fixture_double"):
            self.owner(tunnel=tunnel)

    def test_invalid_port_closes_both_without_running_process(self):
        tunnel, process = TunnelDouble(port=22), ProcessDouble()
        with self.assertRaisesRegex(RuntimeError, "port_invalid"):
            self.owner(tunnel, process).run_once(DOUBLE_AUTHORIZATION)

        self.assertEqual(process.runs, [])
        self.assertEqual((process.closes, tunnel.closes), (1, 1))

    def test_process_failure_or_stderr_closes_everything(self):
        for process in (
            ProcessDouble(fail=True),
            ProcessDouble(ProbeProcessResult(0, output(), b"warning")),
            ProcessDouble(ProbeProcessResult(1, b"", b"")),
        ):
            with self.subTest(process=process):
                tunnel = TunnelDouble()
                with self.assertRaises(RuntimeError):
                    self.owner(tunnel, process).run_once(DOUBLE_AUTHORIZATION)
                self.assertEqual((process.closes, tunnel.closes), (1, 1))

    def test_extra_duplicate_or_multiline_output_is_rejected(self):
        duplicate = output()[:-2] + b',"writes":0}\n'
        multiline = output() + b"{}\n"
        for raw in (output(extra={"secret": "x"}), duplicate, multiline):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    self.owner(
                        process=ProcessDouble(ProbeProcessResult(0, raw, b""))
                    ).run_once(DOUBLE_AUTHORIZATION)

    def test_close_failure_is_terminal(self):
        with self.assertRaisesRegex(RuntimeError, "close_failed"):
            self.owner(tunnel=TunnelDouble(close_fail=True)).run_once(
                DOUBLE_AUTHORIZATION
            )

    def test_payload_identity_is_immutable(self):
        with self.assertRaisesRegex(ValueError, "payload_identity_invalid"):
            FixtureOnlyHostProbeTransportOwner(
                payload=PAYLOAD + b" ",
                tunnel=TunnelDouble(),
                process=ProcessDouble(),
            )

    def test_prototype_has_no_production_transport_surface(self):
        text = (
            ROOT / "bitrix_connector" / "r1_key_vault_host_probe_transport.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "subprocess",
            "socket",
            "paramiko",
            "fabric",
            "azure.cli",
            "requests",
            "httpx",
            "password",
            "credential",
            "print(",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
