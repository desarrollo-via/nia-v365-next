"""Execute the exact R1 Key Vault provisioning only after its literal gate."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_owner import (  # noqa: E402
    FIRST_CONFIRMATION_TEXT,
    R1KeyVaultLinuxProvisioningSnapshot,
    SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    build_dormant_real_provisioning_owner,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_provisioning_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH


def _fingerprint() -> str:
    return _local_fingerprint(
        excluded_relative_paths=(REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH)
    )


def _write_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


def _payload(snapshot: R1KeyVaultLinuxProvisioningSnapshot) -> dict[str, object]:
    if type(snapshot) is not R1KeyVaultLinuxProvisioningSnapshot:
        return {"state": "NO-GO-TERMINAL", "category": "invalid_evidence"}
    return asdict(snapshot)


async def _run_exact(
    confirmation: str,
    *,
    owner_factory=build_dormant_real_provisioning_owner,
) -> int:
    if confirmation != SECOND_CONFIRMATION_TEXT:
        payload: dict[str, object] = {
            "state": "AWAITING-SECOND-CONFIRMATION",
            "effects_started": 0,
        }
        _write_report(payload)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    baseline = _fingerprint()
    owner = owner_factory(local_state_guard=lambda: _fingerprint() == baseline)
    prepared = await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
    if prepared.state != "AWAITING-SECOND-CONFIRMATION":
        payload = _payload(prepared)
        payload["local_state_preserved"] = _fingerprint() == baseline
        _write_report(payload)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    result = await owner.execute_once(second_confirmation=confirmation)
    payload = _payload(result)
    payload["local_state_preserved"] = _fingerprint() == baseline
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if result.state == "PROVISIONED-DORMANT-VERIFIED" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run_exact(args.confirmation))
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
