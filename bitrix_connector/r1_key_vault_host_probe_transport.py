"""Fixture-only lifecycle prototype for the future R1 host probe transport."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Protocol


DOUBLE_AUTHORIZATION = "EXECUTE R1 HOST PROBE WITH INJECTED DOUBLES ONLY"
EXPECTED_PAYLOAD_BYTES = 2315
EXPECTED_PAYLOAD_SHA256 = (
    "069FCD51B81F34CA8C08A9EFC4B55D908BC34A7B2A9E2A2EEA726670BA486972"
)
EXPECTED_PACKAGES = {
    "azure-identity": "1.25.3",
    "azure-keyvault-secrets": "4.11.0",
    "aiohttp": "3.14.3",
}
EXPECTED_OUTPUT_KEYS = {
    "schema",
    "packages",
    "setting_present",
    "setting_valid",
    "external_calls",
    "writes",
}


@dataclass(frozen=True)
class ProbeProcessResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class SanitizedHostProbeTransportResult:
    packages: dict[str, str]
    setting_present: bool
    setting_valid: Optional[bool]
    tunnel_opens: int
    process_runs: int
    retries: int
    closed: bool


class FixtureTunnel(Protocol):
    kind: str

    def open_exact(
        self,
        *,
        subscription_id: str,
        resource_group: str,
        app_name: str,
        slot: str,
        timeout_seconds: int,
    ) -> int: ...

    def close(self) -> None: ...


class FixtureProbeProcess(Protocol):
    kind: str

    def run_exact(
        self,
        *,
        host: str,
        port: int,
        argv: tuple[str, str],
        stdin: bytes,
        timeout_seconds: int,
    ) -> ProbeProcessResult: ...

    def close(self) -> None: ...


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("r1_host_probe_output_duplicate_key")
        result[key] = value
    return result


def _validate_output(raw: bytes) -> tuple[dict[str, str], bool, Optional[bool]]:
    if type(raw) is not bytes or not raw or len(raw) > 1024:
        raise ValueError("r1_host_probe_output_size_invalid")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("r1_host_probe_output_encoding_invalid") from error
    if text.count("\n") > 1 or ("\n" in text and not text.endswith("\n")):
        raise ValueError("r1_host_probe_output_line_invalid")
    try:
        payload = json.loads(text, object_pairs_hook=_object_without_duplicates)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("r1_host_probe_output_json_invalid") from error
    if type(payload) is not dict or set(payload) != EXPECTED_OUTPUT_KEYS:
        raise ValueError("r1_host_probe_output_shape_invalid")
    packages = payload["packages"]
    present = payload["setting_present"]
    valid = payload["setting_valid"]
    if (
        payload["schema"] != "nia-next-r1-host-probe-v1"
        or type(packages) is not dict
        or packages != EXPECTED_PACKAGES
        or type(present) is not bool
        or (present and valid is not True)
        or (not present and valid is not None)
        or payload["external_calls"] != 0
        or payload["writes"] != 0
    ):
        raise ValueError("r1_host_probe_output_evidence_invalid")
    return dict(packages), present, valid


class FixtureOnlyHostProbeTransportOwner:
    """Runs one exact lifecycle only when both dependencies identify as doubles."""

    __slots__ = ("_payload", "_process", "_tunnel", "_used")

    def __init__(
        self,
        *,
        payload: bytes,
        tunnel: FixtureTunnel,
        process: FixtureProbeProcess,
    ) -> None:
        if (
            type(payload) is not bytes
            or len(payload) != EXPECTED_PAYLOAD_BYTES
            or hashlib.sha256(payload).hexdigest().upper()
            != EXPECTED_PAYLOAD_SHA256
        ):
            raise ValueError("r1_host_probe_payload_identity_invalid")
        if getattr(tunnel, "kind", None) != "fixture-double":
            raise TypeError("r1_host_probe_tunnel_not_fixture_double")
        if getattr(process, "kind", None) != "fixture-double":
            raise TypeError("r1_host_probe_process_not_fixture_double")
        self._payload = payload
        self._tunnel: Optional[FixtureTunnel] = tunnel
        self._process: Optional[FixtureProbeProcess] = process
        self._used = False

    def run_once(self, authorization: str) -> SanitizedHostProbeTransportResult:
        tunnel, self._tunnel = self._tunnel, None
        process, self._process = self._process, None
        if (
            self._used
            or authorization != DOUBLE_AUTHORIZATION
            or tunnel is None
            or process is None
        ):
            self._used = True
            raise RuntimeError("r1_host_probe_transport_reuse_or_auth_invalid")
        self._used = True
        process_runs = 0
        tunnel_opens = 0
        failures = 0
        evidence: Optional[tuple[dict[str, str], bool, Optional[bool]]] = None
        try:
            port = tunnel.open_exact(
                subscription_id="0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9",
                resource_group="nia-v365-next-api_group",
                app_name="nia-v365-next-api",
                slot="Production",
                timeout_seconds=30,
            )
            tunnel_opens = 1
            if type(port) is not int or not 1024 <= port <= 65535:
                raise RuntimeError("r1_host_probe_tunnel_port_invalid")
            result = process.run_exact(
                host="127.0.0.1",
                port=port,
                argv=("python", "-"),
                stdin=self._payload,
                timeout_seconds=15,
            )
            process_runs = 1
            if (
                type(result) is not ProbeProcessResult
                or result.exit_code != 0
                or result.stderr != b""
            ):
                raise RuntimeError("r1_host_probe_process_failed")
            evidence = _validate_output(result.stdout)
        finally:
            for resource in (process, tunnel):
                try:
                    resource.close()
                except BaseException:
                    failures += 1
        if failures:
            raise RuntimeError("r1_host_probe_transport_close_failed")
        if evidence is None:
            raise RuntimeError("r1_host_probe_evidence_missing")
        packages, present, valid = evidence
        return SanitizedHostProbeTransportResult(
            packages=packages,
            setting_present=present,
            setting_valid=valid,
            tunnel_opens=tunnel_opens,
            process_runs=process_runs,
            retries=0,
            closed=True,
        )


__all__ = [
    "DOUBLE_AUTHORIZATION",
    "FixtureOnlyHostProbeTransportOwner",
    "ProbeProcessResult",
    "SanitizedHostProbeTransportResult",
]
