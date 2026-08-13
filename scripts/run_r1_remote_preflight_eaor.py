"""Exact launcher for the accepted 2026-08-13 remote read-only EAOR.

This module is safe to import.  External work begins only from ``main`` or
``run_exact_once`` after all exact CLI gates are supplied.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

from bitrix_connector.r1_result_eaor_remote_preflight_coordinator import (
    REMOTE_PREFLIGHT_ACCEPTANCE,
    REMOTE_PREFLIGHT_EAOR_ID,
)
from bitrix_connector.r1_result_eaor_remote_preflight_real_binding import (
    build_dormant_real_remote_preflight_binding,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint


ROOT = Path(__file__).resolve().parents[1]
REPORT_RELATIVE_PATH = Path(
    ".tmp/r1_remote_preflight_eaor_2026-08-13_latest.json"
)
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH

_ALLOWED_STATES = frozenset({
    "NO-GO-ACCEPTANCE", "NO-GO-EXPIRED", "GO-REMOTE-PREFLIGHT",
    "ATTENTION-REQUIRED-AZURE-AUTHENTICATION",
    "NO-GO-BUDGET-EXHAUSTED", "NO-GO-TERMINAL",
})
_ALLOWED_CATEGORIES = frozenset({
    "none", "authentication", "authorization", "not_found", "transport",
    "unknown", "drift", "invalid_evidence", "resource_close_failed",
    "launcher_failure",
})


def fingerprint() -> str:
    return _local_fingerprint(excluded_relative_paths=(
        REPORT_RELATIVE_PATH, REPORT_TEMP_RELATIVE_PATH,
    ))


def sanitize_result(snapshot: object, *, local_state_preserved: bool) -> dict:
    raw = asdict(snapshot) if hasattr(snapshot, "__dataclass_fields__") else {}
    state = raw.get("state")
    category = raw.get("category")
    counts_valid = all(
        type(raw.get(name)) is int and raw[name] >= 0
        for name in ("attempts_started", "read_calls", "health_pairs")
    )
    if (
        state not in _ALLOWED_STATES
        or category not in _ALLOWED_CATEGORIES
        or not counts_valid
        or type(raw.get("resources_closed")) is not bool
    ):
        state = "NO-GO-TERMINAL"
        category = "invalid_evidence"
        raw = {
            "attempts_started": 0, "read_calls": 0, "health_pairs": 0,
            "resources_closed": False,
        }
    if not local_state_preserved:
        state = "NO-GO-TERMINAL"
        category = "drift"
    return {
        "eaor_id": REMOTE_PREFLIGHT_EAOR_ID,
        "state": state,
        "category": category,
        "attempts_started": raw["attempts_started"],
        "read_calls": raw["read_calls"],
        "health_pairs": raw["health_pairs"],
        "resources_closed": raw["resources_closed"],
        "local_state_preserved": local_state_preserved,
        "mutations": 0,
        "protected_source_opens": 0,
        "secret_reads": 0,
        "app_setting_lists": 0,
        "broad_resource_lists": 0,
        "bitrix_calls": 0,
        "messages_sent": 0,
    }


def write_sanitized_report(
    payload: dict,
    *,
    report_path: Path | None = None,
    temp_path: Path | None = None,
) -> None:
    selected_report = report_path or REPORT_PATH
    selected_temp = temp_path or REPORT_TEMP_PATH
    selected_report.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    selected_temp.write_bytes(encoded + b"\n")
    selected_temp.replace(selected_report)


async def run_exact_once(
    *,
    acceptance: str,
    current_day: str,
    binding_factory=build_dormant_real_remote_preflight_binding,
    fingerprint_reader=fingerprint,
    report_writer=write_sanitized_report,
) -> dict:
    baseline = fingerprint_reader()
    binding = binding_factory(
        local_state_guard=lambda: fingerprint_reader() == baseline
    )
    coordinator = binding.build_coordinator_once()
    snapshot = await coordinator.run_once(
        acceptance=acceptance,
        current_day=current_day,
    )
    preserved = fingerprint_reader() == baseline
    payload = sanitize_result(snapshot, local_state_preserved=preserved)
    report_writer(payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eaor-id", required=True, choices=(REMOTE_PREFLIGHT_EAOR_ID,)
    )
    parser.add_argument(
        "--acceptance", required=True, choices=(REMOTE_PREFLIGHT_ACCEPTANCE,)
    )
    return parser


def main(argv=None, *, executor=run_exact_once) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = asyncio.run(executor(
            acceptance=args.acceptance,
            current_day=date.today().isoformat(),
        ))
    except BaseException:
        payload = {
            "eaor_id": REMOTE_PREFLIGHT_EAOR_ID,
            "state": "NO-GO-TERMINAL",
            "category": "launcher_failure",
        }
        try:
            write_sanitized_report(payload)
        except BaseException:
            pass
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    if payload.get("state") == "GO-REMOTE-PREFLIGHT":
        return 0
    if payload.get("state") == "ATTENTION-REQUIRED-AZURE-AUTHENTICATION":
        return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
