"""Reduce one exact failed-vault Activity Log detail to sanitary cause fields."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    SanitizedCommandResult,
    VAULT_CREATE_CAUSE_ACTIVITY,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_create_cause_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH
MAX_READS = 1
ERROR_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,79}$")


def _fingerprint() -> str:
    return _local_fingerprint(
        excluded_relative_paths=(REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH)
    )


def _write_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


def _find_code(value: object) -> str:
    if type(value) is dict:
        direct = value.get("code")
        if type(direct) is str and ERROR_CODE.fullmatch(direct):
            return direct
        for child in value.values():
            found = _find_code(child)
            if found:
                return found
    elif type(value) is list:
        for child in value:
            found = _find_code(child)
            if found:
                return found
    return ""


def _category(code: str) -> str:
    lowered = code.casefold()
    if any(marker in lowered for marker in ("authoriz", "forbidden", "denied")):
        return "authorization"
    if any(marker in lowered for marker in ("already", "conflict", "inuse")):
        return "conflict"
    if any(marker in lowered for marker in ("invalid", "badrequest")):
        return "invalid_request"
    if any(marker in lowered for marker in ("quota", "limit", "capacity")):
        return "quota"
    if any(marker in lowered for marker in ("notfound", "not_found")):
        return "not_found"
    return "azure_other" if code else "unknown"


def _sanitize(result: object) -> dict[str, object]:
    if type(result) is not SanitizedCommandResult:
        return {"state": "NO-GO-INVALID-EVIDENCE"}
    if result.return_code != 0:
        category = result.failure_category
        if category not in {
            "authentication", "authorization", "not_found", "transport", "unknown"
        }:
            category = "unknown"
        return {"state": "NO-GO-READ-FAILED", "category": category}
    try:
        detail = json.loads(result.stdout)
        if type(detail) is str:
            detail = json.loads(detail)
    except (TypeError, ValueError):
        return {"state": "NO-GO-INVALID-EVIDENCE"}
    code = _find_code(detail)
    if not code:
        return {"state": "CAUSE-INCONCLUSIVE", "category": "unknown"}
    return {
        "state": "FAILED-WRITE-CAUSE-FOUND",
        "category": _category(code),
        "error_code": code,
    }


async def _run(*, runner_factory=ExactAzureCliCommandRunner) -> int:
    baseline = _fingerprint()
    runner = runner_factory()
    result = None
    resources_closed = True
    try:
        result = await runner.run_exact_once(VAULT_CREATE_CAUSE_ACTIVITY)
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
    return 0 if payload["state"] == "FAILED-WRITE-CAUSE-FOUND" else 2


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
