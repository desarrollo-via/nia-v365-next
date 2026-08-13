"""Verify only the exact soft-deleted R1 vault with one Azure read."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_owner import VAULT_ID  # noqa: E402
from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    SanitizedCommandResult,
    VAULT_DELETED_SHOW,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402
from scripts.run_r1_key_vault_rollback_postread import (  # noqa: E402
    _deleted_exact,
    _sanitized_state,
)


REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_deleted_postread_latest.json")
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


async def _run(*, runner_factory=ExactAzureCliCommandRunner) -> int:
    baseline = _fingerprint()
    runner = runner_factory()
    result = None
    resources_closed = True
    try:
        result = await runner.run_exact_once(VAULT_DELETED_SHOW)
    except BaseException:
        pass
    finally:
        try:
            await runner.close()
        except BaseException:
            resources_closed = False
    exact = _deleted_exact(result)
    absent = (
        type(result) is SanitizedCommandResult
        and result.return_code != 0
        and result.stdout == ""
        and result.failure_category == "not_found"
    )
    verified = (exact or absent) and resources_closed
    payload = {
        "state": (
            "ROLLBACK-VERIFIED-SOFT-DELETED"
            if verified and exact
            else "ROLLBACK-VERIFIED-NO-RESOURCE"
            if verified
            else "NO-GO-REMAINDER"
        ),
        "read_calls": MAX_READS,
        "soft_deleted_vault_exact": exact,
        "soft_deleted_vault_absent": absent,
        "soft_deleted_read_state": _sanitized_state(result, expected=VAULT_ID),
        "active_vault_absence_reused": True,
        "resources_closed": resources_closed,
        "local_state_preserved": _fingerprint() == baseline,
        "mutations": 0,
        "secret_reads": 0,
        "purge_calls": 0,
        "provisioning_retries": 0,
    }
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if verified else 2


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
