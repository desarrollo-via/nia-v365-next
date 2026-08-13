"""Read the exact, time-bounded activity evidence for the failed vault create."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    SanitizedCommandResult,
    VAULT_CREATE_ACTIVITY,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_create_activity_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH
MAX_READS = 1
MAX_EVENTS = 5
WRITE_OPERATION = "Microsoft.KeyVault/vaults/write"


def _fingerprint() -> str:
    return _local_fingerprint(
        excluded_relative_paths=(REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH)
    )


def _write_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


def _value(item: object) -> str:
    if type(item) is dict and type(item.get("value")) is str:
        return item["value"]
    return item if type(item) is str else ""


def _sanitize(result: object) -> dict[str, object]:
    if type(result) is not SanitizedCommandResult:
        return {"state": "NO-GO-INVALID-EVIDENCE", "event_count": 0}
    if result.return_code != 0:
        category = result.failure_category
        if category not in {
            "authentication", "authorization", "not_found", "transport", "unknown"
        }:
            category = "unknown"
        return {"state": "NO-GO-READ-FAILED", "category": category, "event_count": 0}
    try:
        events = json.loads(result.stdout)
    except (TypeError, ValueError):
        return {"state": "NO-GO-INVALID-EVIDENCE", "event_count": 0}
    if type(events) is not list or len(events) > MAX_EVENTS:
        return {"state": "NO-GO-INVALID-EVIDENCE", "event_count": 0}
    failed = 0
    write_events = 0
    for event in events:
        if type(event) is not dict:
            return {"state": "NO-GO-INVALID-EVIDENCE", "event_count": 0}
        operation = _value(event.get("operationName"))
        status = _value(event.get("status")).casefold()
        if operation.casefold() == WRITE_OPERATION.casefold():
            write_events += 1
            if status == "failed":
                failed += 1
    state = (
        "FAILED-WRITE-ACTIVITY-FOUND"
        if failed
        else "NO-ARM-ACTIVITY"
        if not events
        else "ACTIVITY-INCONCLUSIVE"
    )
    return {
        "state": state,
        "event_count": len(events),
        "write_event_count": write_events,
        "failed_write_event_count": failed,
    }


async def _run(*, runner_factory=ExactAzureCliCommandRunner) -> int:
    baseline = _fingerprint()
    runner = runner_factory()
    result = None
    resources_closed = True
    try:
        result = await runner.run_exact_once(VAULT_CREATE_ACTIVITY)
    except BaseException:
        pass
    finally:
        try:
            await runner.close()
        except BaseException:
            resources_closed = False
    payload = _sanitize(result)
    payload.update(
        {
            "read_calls": MAX_READS,
            "resources_closed": resources_closed,
            "local_state_preserved": _fingerprint() == baseline,
            "mutations": 0,
            "secret_reads": 0,
            "provisioning_retries": 0,
        }
    )
    if not resources_closed:
        payload["state"] = "NO-GO-RESOURCE-CLOSE"
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if payload["state"] in {
        "FAILED-WRITE-ACTIVITY-FOUND", "NO-ARM-ACTIVITY"
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
