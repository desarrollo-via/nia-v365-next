"""Read the exact Microsoft.KeyVault provider registration state once."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    KEY_VAULT_PROVIDER_SHOW,
    SanitizedCommandResult,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_provider_preflight_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH
MAX_READS = 1
KNOWN_STATES = {"Registered", "NotRegistered", "Registering", "Unregistering"}


def _fingerprint() -> str:
    return _local_fingerprint(
        excluded_relative_paths=(REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH)
    )


def _write_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


def _sanitize(result: object) -> dict[str, object]:
    if type(result) is not SanitizedCommandResult:
        return {"state": "NO-GO-INVALID-EVIDENCE", "provider_state": "unknown"}
    if result.return_code != 0:
        category = result.failure_category
        if category not in {
            "authentication", "authorization", "not_found", "transport", "unknown"
        }:
            category = "unknown"
        return {
            "state": "NO-GO-READ-FAILED",
            "provider_state": "unknown",
            "category": category,
        }
    provider_state = result.stdout.strip()
    if provider_state not in KNOWN_STATES:
        return {"state": "NO-GO-INVALID-EVIDENCE", "provider_state": "unknown"}
    state = (
        "PROVIDER-REGISTERED"
        if provider_state == "Registered"
        else "PROVIDER-NOT-REGISTERED"
        if provider_state == "NotRegistered"
        else "NO-GO-PROVIDER-TRANSITIONING"
    )
    return {"state": state, "provider_state": provider_state}


async def _run(*, runner_factory=ExactAzureCliCommandRunner) -> int:
    baseline = _fingerprint()
    runner = runner_factory()
    result = None
    resources_closed = True
    try:
        result = await runner.run_exact_once(KEY_VAULT_PROVIDER_SHOW)
    except BaseException:
        pass
    finally:
        try:
            await runner.close()
        except BaseException:
            resources_closed = False
    payload = _sanitize(result)
    payload.update({
        "read_calls": MAX_READS,
        "resources_closed": resources_closed,
        "local_state_preserved": _fingerprint() == baseline,
        "mutations": 0,
        "secret_reads": 0,
        "provisioning_retries": 0,
    })
    if not resources_closed:
        payload["state"] = "NO-GO-RESOURCE-CLOSE"
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if payload["state"] in {
        "PROVIDER-REGISTERED", "PROVIDER-NOT-REGISTERED"
    } else 2


def main() -> int:
    try:
        return asyncio.run(_run())
    except BaseException:
        payload = {"state": "NO-GO-LAUNCHER", "category": "launcher_failure"}
        try:
            _write_report(payload)
        except BaseException:
            pass
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
