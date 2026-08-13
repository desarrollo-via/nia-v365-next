"""Run one authorized, sanitized Azure operator-identity read."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    OPERATOR_SHOW,
    SanitizedCommandResult,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


REPORT_RELATIVE_PATH = Path(".tmp/r1_azure_operator_diagnostic_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH
MAX_READS = 1


def _fingerprint() -> str:
    return _local_fingerprint(
        excluded_relative_paths=(REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH)
    )


def _write_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


def _classify(result: object) -> tuple[str, str]:
    if type(result) is not SanitizedCommandResult:
        return "NO-GO-TERMINAL", "invalid_evidence"
    if result.return_code != 0:
        if result.failure_category == "authentication":
            return "ATTENTION-REQUIRED-AZURE-AUTHENTICATION", "authentication"
        if result.failure_category in {"authorization", "not_found"}:
            return "NO-GO-TERMINAL", result.failure_category
        return "NO-GO-BUDGET-EXHAUSTED", (
            result.failure_category
            if result.failure_category in {"transport", "unknown"}
            else "unknown"
        )
    try:
        uuid.UUID(result.stdout)
    except (ValueError, TypeError):
        return "NO-GO-TERMINAL", "invalid_evidence"
    return "GO", "none"


async def _run(*, runner_factory=ExactAzureCliCommandRunner) -> int:
    baseline = _fingerprint()
    runner = runner_factory()
    result = None
    resources_closed = True
    try:
        result = await runner.run_exact_once(OPERATOR_SHOW)
    except BaseException:
        result = None
    finally:
        try:
            await runner.close()
        except BaseException:
            resources_closed = False
    state, category = _classify(result)
    if not resources_closed:
        state, category = "NO-GO-TERMINAL", "resource_close_failed"
    payload = {
        "state": state,
        "category": category,
        "read_calls": MAX_READS,
        "resources_closed": resources_closed,
        "mutations": 0,
        "protected_source_opens": 0,
        "secret_reads": 0,
        "local_state_preserved": _fingerprint() == baseline,
    }
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if state == "GO" else 2


def main() -> int:
    try:
        return asyncio.run(_run())
    except BaseException:
        payload = {"state": "NO-GO-TERMINAL", "category": "launcher_failure"}
        try:
            _write_report(payload)
        except BaseException:
            pass
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
