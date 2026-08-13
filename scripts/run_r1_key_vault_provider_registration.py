"""One-shot, literal-gated Microsoft.KeyVault provider registration owner."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (  # noqa: E402
    ExactAzureCliCommandRunner,
    KEY_VAULT_PROVIDER_REGISTER,
    KEY_VAULT_PROVIDER_SHOW,
    SanitizedCommandResult,
)
from scripts.run_r1_azure_diagnostic_envelope import _local_fingerprint  # noqa: E402


CONFIRMATION_TEXT = (
    "REGISTRAR MICROSOFT.KEYVAULT SUSCRIPCION "
    "0C4B9EA3-F35D-4A11-BFE7-794D40CF1EC9 "
    "R1-KV-PROVIDER-2026-08-12-V1 EJECUCION INMEDIATA"
)
REPORT_RELATIVE_PATH = Path(".tmp/r1_key_vault_provider_registration_latest.json")
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


def _state(result: object) -> str:
    if (
        type(result) is SanitizedCommandResult
        and result.return_code == 0
        and result.stdout in {"Registered", "NotRegistered", "Registering", "Unregistering"}
    ):
        return result.stdout
    return "unknown"


def _failure_category(result: object) -> str:
    if type(result) is SanitizedCommandResult and result.return_code != 0:
        category = result.failure_category
        if category in {
            "authentication", "authorization", "not_found", "transport", "unknown"
        }:
            return category
    return "unknown"


async def _exact_call(command: tuple[str, ...], runner_factory) -> tuple[object, bool]:
    runner = runner_factory()
    result = None
    closed = True
    try:
        result = await runner.run_exact_once(command)
    except BaseException:
        pass
    finally:
        try:
            await runner.close()
        except BaseException:
            closed = False
    return result, closed


async def _run_exact(
    confirmation: str, *, runner_factory=ExactAzureCliCommandRunner
) -> int:
    if confirmation != CONFIRMATION_TEXT:
        payload = {
            "state": "NO-GO-CONFIRMATION",
            "read_calls": 0,
            "mutation_calls": 0,
            "postread_calls": 0,
        }
        _write_report(payload)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    baseline = _fingerprint()
    resources_closed = True
    reads = mutations = postreads = 0
    preflight, closed = await _exact_call(KEY_VAULT_PROVIDER_SHOW, runner_factory)
    resources_closed &= closed
    reads += 1
    initial = _state(preflight)
    state = "NO-GO-PREFLIGHT"
    final = initial
    registration_category = "none"
    if initial == "Registered":
        state = "PROVIDER-ALREADY-REGISTERED"
    elif initial == "NotRegistered" and resources_closed:
        registered, closed = await _exact_call(
            KEY_VAULT_PROVIDER_REGISTER, runner_factory
        )
        resources_closed &= closed
        mutations += 1
        if _state(registered) == "Registered" and resources_closed:
            postread, closed = await _exact_call(
                KEY_VAULT_PROVIDER_SHOW, runner_factory
            )
            resources_closed &= closed
            postreads += 1
            final = _state(postread)
            state = (
                "PROVIDER-REGISTRATION-VERIFIED"
                if final == "Registered"
                else "NO-GO-POSTREAD"
            )
        else:
            state = "NO-GO-REGISTRATION"
            registration_category = _failure_category(registered)
    elif initial in {"Registering", "Unregistering"}:
        state = "NO-GO-PROVIDER-TRANSITIONING"

    if not resources_closed:
        state = "NO-GO-RESOURCE-CLOSE"
    payload = {
        "state": state,
        "initial_provider_state": initial,
        "final_provider_state": final,
        "read_calls": reads,
        "mutation_calls": mutations,
        "postread_calls": postreads,
        "resources_closed": resources_closed,
        "local_state_preserved": _fingerprint() == baseline,
        "secret_reads": 0,
        "provisioning_retries": 0,
        "unregister_calls": 0,
        "registration_failure_category": registration_category,
    }
    _write_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if state in {
        "PROVIDER-ALREADY-REGISTERED", "PROVIDER-REGISTRATION-VERIFIED"
    } else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()
    try:
        return asyncio.run(_run_exact(args.confirmation))
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
