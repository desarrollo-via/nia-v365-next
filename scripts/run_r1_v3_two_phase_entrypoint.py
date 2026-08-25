"""Persistent, explicit entrypoint for the R1 V3 human checkpoint."""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Awaitable, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from bitrix_connector.r1_result_eaor_coordinator import R1ResultEaorSnapshot  # noqa: E402
from bitrix_connector.r1_v3_two_phase_runtime import build_dormant_r1_v3_two_phase_runner  # noqa: E402
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402

START_CONFIRMATION = "INICIAR EAOR R1 V3 HASTA ATENCION HUMANA"
RESUME_CONFIRMATION = "CONFIRMAR MENSAJE HUMANO R1 V3 ENVIADO"
CHECKPOINT_RELATIVE = Path(".tmp/r1_v3_attention_receipt.json")
LEDGER_RELATIVE = Path(".tmp/r1_v3_write_budget.json")
_SAFE_FIELDS = frozenset({"state", "eaor_id", "acceptance_calls", "provisioning_calls", "activation_calls", "session_arm_calls", "observation_calls", "activation_restore_calls", "human_message_calls", "resources_closed", "human_message_required_now", "pre_event_lease_state", "external_retries", "failure_stage", "failure_category"})

def _sanitized(snapshot: R1ResultEaorSnapshot) -> dict:
    if type(snapshot) is not R1ResultEaorSnapshot: raise TypeError("r1_v3_entrypoint_snapshot_invalid")
    values = asdict(snapshot)
    return {name: values[name] for name in _SAFE_FIELDS}

async def run_persistent_once(*, controller, human_decision: Callable[[], Awaitable[str]]) -> R1ResultEaorSnapshot:
    receipt = await controller.start_until_human_once()
    if not (receipt.state == "ATTENTION-REQUIRED" and receipt.human_message_required_now is True and receipt.pre_event_lease_state == "AWAITING-EVENT"):
        raise RuntimeError("r1_v3_entrypoint_attention_invalid")
    try: decision = await human_decision()
    except BaseException: return await controller.close_waiting_once()
    if decision != RESUME_CONFIRMATION: return await controller.close_waiting_once()
    return await controller.resume_after_human_once()

async def _console_decision() -> str:
    return await asyncio.to_thread(input, "Confirmacion humana: ")

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-code", required=True)
    parser.add_argument("--expected-deployed-sha", required=True)
    parser.add_argument("--expected-deployed-tree", required=True)
    return parser

def main(argv=None, *, builder=build_dormant_r1_v3_two_phase_runner) -> int:
    args = _parser().parse_args(argv)
    if args.confirm_code != START_CONFIRMATION:
        print(json.dumps({"state": "NO-GO-CONFIRMATION"}, sort_keys=True)); return 2
    excluded = (CHECKPOINT_RELATIVE, CHECKPOINT_RELATIVE.with_suffix(".tmp"), LEDGER_RELATIVE, LEDGER_RELATIVE.with_suffix(".tmp"))
    baseline = _local_fingerprint(excluded_relative_paths=excluded)
    controller = builder(checkpoint_path=ROOT / CHECKPOINT_RELATIVE, ledger_path=ROOT / LEDGER_RELATIVE, expected_deployed_sha=args.expected_deployed_sha, expected_deployed_tree=args.expected_deployed_tree, local_state_guard=lambda: _local_fingerprint(excluded_relative_paths=excluded) == baseline)
    try: result = asyncio.run(run_persistent_once(controller=controller, human_decision=_console_decision))
    except BaseException:
        print(json.dumps({"state": "NO-GO-ENTRYPOINT"}, sort_keys=True)); return 3
    print(json.dumps(_sanitized(result), sort_keys=True))
    return 0 if result.state == "VERIFIED-RESTORED" else 2

if __name__ == "__main__": raise SystemExit(main())
