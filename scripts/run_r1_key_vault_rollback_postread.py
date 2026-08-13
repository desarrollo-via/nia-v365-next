"""Verify the exact R1 vault rollback with two read-only Azure calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_owner import (  # noqa: E402
    VAULT_ID,
    VAULT_NAME,
)
from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    SanitizedCommandResult,
    VAULT_DELETED_SHOW,
    VAULT_SHOW,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_rollback_postread_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH
MAX_READS = 2


def _fingerprint() -> str:
    return _local_fingerprint(
        excluded_relative_paths=(REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH)
    )


def _write_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


def _active_absent(result: object) -> bool:
    return (
        type(result) is SanitizedCommandResult
        and result.return_code != 0
        and result.stdout == ""
        and result.failure_category == "not_found"
    )


def _deleted_exact(result: object) -> bool:
    return (
        type(result) is SanitizedCommandResult
        and result.return_code == 0
        and result.stdout == VAULT_ID
    )


def _sanitized_state(result: object, *, expected: str) -> str:
    if type(result) is not SanitizedCommandResult:
        return "invalid_evidence"
    if result.return_code == 0:
        return "exact" if result.stdout == expected else "invalid_output"
    if result.failure_category in {
        "authentication", "authorization", "not_found", "transport", "unknown"
    }:
        return result.failure_category
    return "unknown"


async def _run(*, runner_factory=ExactAzureCliCommandRunner) -> int:
    baseline = _fingerprint()
    runner = runner_factory()
    reads = 0
    active = deleted = None
    resources_closed = True
    try:
        reads += 1
        active = await runner.run_exact_once(VAULT_SHOW)
        reads += 1
        deleted = await runner.run_exact_once(VAULT_DELETED_SHOW)
    except BaseException:
        pass
    finally:
        try:
            await runner.close()
        except BaseException:
            resources_closed = False
    active_absent = _active_absent(active)
    deleted_exact = _deleted_exact(deleted)
    deleted_absent = (
        type(deleted) is SanitizedCommandResult
        and deleted.return_code != 0
        and deleted.stdout == ""
        and deleted.failure_category == "not_found"
    )
    restored = active_absent and (deleted_exact or deleted_absent) and resources_closed
    payload = {
        "state": (
            "ROLLBACK-VERIFIED-SOFT-DELETED"
            if restored and deleted_exact
            else "ROLLBACK-VERIFIED-NO-RESOURCE"
            if restored
            else "NO-GO-REMAINDER"
        ),
        "read_calls": reads,
        "active_vault_absent": active_absent,
        "active_read_state": (
            "absent"
            if active_absent
            else _sanitized_state(active, expected=VAULT_ID)
        ),
        "soft_deleted_vault_exact": deleted_exact,
        "soft_deleted_vault_absent": deleted_absent,
        "soft_deleted_read_state": _sanitized_state(
            deleted, expected=VAULT_ID
        ),
        "resources_closed": resources_closed,
        "local_state_preserved": _fingerprint() == baseline,
        "mutations": 0,
        "secret_reads": 0,
        "purge_calls": 0,
        "provisioning_retries": 0,
    }
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if restored else 2


def main() -> int:
    try:
        return asyncio.run(_run())
    except BaseException:
        payload = {"state": "NO-GO-REMAINDER", "category": "launcher_failure"}
        try:
            _write_report(payload)
        except BaseException:
            pass
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
