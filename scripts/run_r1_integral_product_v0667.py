"""Final one-shot R1 launcher; inert unless the exact successor is accepted."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_integral_product_runtime import (  # noqa: E402
    ExactR1SharedReviewRuntime,
    PersistentOneShotBearerSecretSink,
    build_integral_product_factory_binding,
)
from bitrix_connector.r1_result_eaor_coordinator import EAOR_ACCEPTANCE  # noqa: E402
from bitrix_connector.r1_result_eaor_product_launcher import (  # noqa: E402
    R1ResultEaorProductLauncher,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


EXECUTION_CONFIRMATION = (
    "EJECUTAR NIA-NEXT R1 INTEGRAL V0667 PUT-BEARER HASTA RESULTADO"
)
REPORT_RELATIVE = Path(".tmp/r1_integral_product_v0667_latest.json")
LEDGER_RELATIVE = Path(".tmp/r1_integral_product_v0667_write_budget.json")
REPORT_PATH = ROOT / REPORT_RELATIVE
LEDGER_PATH = ROOT / LEDGER_RELATIVE


def _fingerprint() -> str:
    return _local_fingerprint(excluded_relative_paths=(
        REPORT_RELATIVE, REPORT_RELATIVE.with_suffix(".tmp"),
        LEDGER_RELATIVE, LEDGER_RELATIVE.with_suffix(".tmp"),
    ))


def _write_report(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(REPORT_PATH)


def _sanitized(snapshot) -> dict:
    values = asdict(snapshot)
    allowlist = {
        "state", "stage", "resources_closed", "human_message_required_now",
        "pre_event_lease_state", "provisioning_state", "activation_state",
        "session_state", "restoration_state",
    }
    return {name: values[name] for name in allowlist if name in values}


async def _run() -> int:
    baseline = _fingerprint()
    shared = ExactR1SharedReviewRuntime(
        expected_deployed_sha=_EXPECTED_SHA,
        expected_deployed_tree=_EXPECTED_TREE,
    )
    sink = PersistentOneShotBearerSecretSink(ledger_path=LEDGER_PATH)
    binding = build_integral_product_factory_binding(
        local_state_guard=lambda: _fingerprint() == baseline,
        shared_review_runtime=shared,
        provisioning_sink=sink,
    )
    runner = R1ResultEaorProductLauncher(
        current_day="2026-08-13"
    ).build_runner_from_binding_once(
        acceptance=EAOR_ACCEPTANCE,
        binding=binding,
    )
    waiting = await runner.run_until_human_once()
    waiting_payload = _sanitized(waiting)
    waiting_payload["local_state_preserved"] = _fingerprint() == baseline
    waiting_payload["write_checkpoint_succeeded"] = sink.checkpoint_succeeded()
    _write_report(waiting_payload)
    print(json.dumps(waiting_payload, separators=(",", ":"), sort_keys=True), flush=True)
    if waiting.state != "ATTENTION-REQUIRED":
        return 2
    terminal = await runner.resume_after_human_once()
    payload = _sanitized(terminal)
    payload["local_state_preserved"] = _fingerprint() == baseline
    payload["write_checkpoint_succeeded"] = sink.checkpoint_succeeded()
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)
    return 0 if terminal.state == "VERIFIED-RESTORED" else 2


def main(argv=None) -> int:
    global _EXPECTED_SHA, _EXPECTED_TREE
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-code", required=True)
    parser.add_argument("--expected-deployed-sha", required=True)
    parser.add_argument("--expected-deployed-tree", required=True)
    args = parser.parse_args(argv)
    if args.confirm_code != EXECUTION_CONFIRMATION:
        payload = {"state": "NO-GO-CONFIRMATION"}
        _write_report(payload)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2
    _EXPECTED_SHA = args.expected_deployed_sha
    _EXPECTED_TREE = args.expected_deployed_tree
    try:
        ExactR1SharedReviewRuntime(
            expected_deployed_sha=_EXPECTED_SHA,
            expected_deployed_tree=_EXPECTED_TREE,
        )
    except (TypeError, ValueError):
        payload = {"state": "NO-GO-DEPLOYMENT-IDENTITY"}
        _write_report(payload)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2
    try:
        return asyncio.run(_run())
    except BaseException:
        payload = {"state": "NO-GO-INTEGRAL-LAUNCHER"}
        try:
            _write_report(payload)
        except BaseException:
            pass
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
