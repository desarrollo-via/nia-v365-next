"""Run the authorized, sanitized R1 Azure read-only diagnostic envelope."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORT_RELATIVE_PATH = Path(".tmp/r1_azure_diagnostic_latest.json")
REPORT_TEMP_RELATIVE_PATH = REPORT_RELATIVE_PATH.with_suffix(".tmp")
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
REPORT_TEMP_PATH = ROOT / REPORT_TEMP_RELATIVE_PATH
MAX_ATTEMPTS = 1

from bitrix_connector.r1_azure_diagnostic_real_attempt import (  # noqa: E402
    build_real_r1_azure_diagnostic_coordinator,
)


def _git_bytes(*args: str) -> bytes:
    result = subprocess.run(
        ("git", "-c", f"safe.directory={ROOT.as_posix()}", *args),
        cwd=ROOT,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    return result.stdout


def _local_fingerprint(
    *, excluded_relative_paths: tuple[Path, ...] = ()
) -> str:
    digest = hashlib.sha256()
    digest.update(_git_bytes("rev-parse", "HEAD"))
    digest.update(_git_bytes("diff", "--binary", "--no-ext-diff", "HEAD", "--", "."))
    excluded = {
        REPORT_RELATIVE_PATH.as_posix(),
        REPORT_TEMP_RELATIVE_PATH.as_posix(),
        *(path.as_posix() for path in excluded_relative_paths),
    }
    untracked = _git_bytes(
        "ls-files", "--others", "--exclude-standard", "-z", "--", "."
    )
    for raw_path in sorted(path for path in untracked.split(b"\0") if path):
        relative = raw_path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        if relative in excluded:
            continue
        candidate = ROOT / relative
        if not candidate.is_file():
            continue
        digest.update(raw_path)
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_sanitized_report(payload: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    REPORT_TEMP_PATH.write_bytes(encoded + b"\n")
    REPORT_TEMP_PATH.replace(REPORT_PATH)


async def _run() -> int:
    baseline = _local_fingerprint()
    coordinator = build_real_r1_azure_diagnostic_coordinator(
        local_state_guard=lambda: _local_fingerprint() == baseline,
        max_attempts=MAX_ATTEMPTS,
    )
    result = await coordinator.run_once()
    payload = {
        "state": result.state,
        "category": result.category,
        "attempts_started": result.attempts_started,
        "read_calls": result.read_calls,
        "health_pairs": result.health_pairs,
        "resources_closed": result.resources_closed,
        "mutations": result.mutations,
        "protected_source_opens": result.protected_source_opens,
        "secret_reads": result.secret_reads,
        "local_state_preserved": _local_fingerprint() == baseline,
    }
    _write_sanitized_report(payload)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if result.state == "GO" else 2


def main() -> int:
    try:
        return asyncio.run(_run())
    except BaseException:
        payload = {"state": "NO-GO-TERMINAL", "category": "launcher_failure"}
        try:
            _write_sanitized_report(payload)
        except BaseException:
            pass
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
