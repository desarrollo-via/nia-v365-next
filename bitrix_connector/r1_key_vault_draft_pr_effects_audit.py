"""Public one-shot audit of four sanitized GitHub effect counts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY = "desarrollo-via/nia-v365-next"
EXPECTED_HEAD = "codex/r1-keyvault-dormant-v0551"
EXPECTED_SHA = "e6af8b390f401dd3f2934faf2ced3ed70002e7bf"
API_BASE = f"https://api.github.com/repos/{REPOSITORY}"


class EffectsAuditInputError(ValueError):
    pass


class EffectsAuditTransportError(RuntimeError):
    pass


class JsonGetTransport(Protocol):
    def get_json(self, url: str) -> tuple[int, Any]: ...


class PublicJsonGetTransport:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("effects_audit_timeout_invalid")
        self._timeout_seconds = timeout_seconds

    def get_json(self, url: str) -> tuple[int, Any]:
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "nia-next-r1-effects-audit",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return int(response.status), json.load(response)
        except HTTPError as error:
            raise EffectsAuditTransportError(
                f"effects_audit_http_{error.code}"
            ) from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EffectsAuditTransportError(
                "effects_audit_transport_or_json_error"
            ) from error


@dataclass(frozen=True)
class EffectsAuditResult:
    decision: str
    associated_prs: int
    actions: int
    checks: int
    statuses: int
    requests: int = 5
    retries: int = 0
    external_writes: int = 0


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EffectsAuditInputError(f"{label}_must_be_array")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EffectsAuditInputError(f"{label}_must_be_object")
    return value


def _count(value: Any, label: str) -> int:
    mapping = _object(value, label)
    count = mapping.get("total_count")
    if type(count) is not int or count < 0:
        raise EffectsAuditInputError(f"{label}_count_invalid")
    return count


def _pr_numbers(value: Any, label: str) -> set[int]:
    numbers: set[int] = set()
    for item in _array(value, label):
        mapping = _object(item, f"{label}_item")
        number = mapping.get("number")
        head = mapping.get("head")
        if type(number) is not int or not isinstance(head, Mapping):
            raise EffectsAuditInputError(f"{label}_identity_invalid")
        if head.get("ref") != EXPECTED_HEAD or head.get("sha") != EXPECTED_SHA:
            raise EffectsAuditInputError(f"{label}_scope_invalid")
        numbers.add(number)
    return numbers


def evaluate_effects_payloads(payloads: Mapping[str, Any]) -> EffectsAuditResult:
    if not isinstance(payloads, Mapping):
        raise EffectsAuditInputError("payloads_must_be_mapping")
    prs = _pr_numbers(payloads.get("head_prs"), "head_prs")
    prs.update(_pr_numbers(payloads.get("commit_prs"), "commit_prs"))
    actions = _count(payloads.get("actions"), "actions")
    checks = _count(payloads.get("checks"), "checks")
    statuses_payload = _object(payloads.get("statuses"), "statuses")
    statuses = len(_array(statuses_payload.get("statuses"), "statuses_items"))
    decision = (
        "EFFECTS-ABSENT"
        if not prs and actions == checks == statuses == 0
        else "EFFECTS-PRESENT"
    )
    return EffectsAuditResult(
        decision=decision,
        associated_prs=len(prs),
        actions=actions,
        checks=checks,
        statuses=statuses,
    )


def collect_effects_once(transport: JsonGetTransport) -> EffectsAuditResult:
    if transport is None or not callable(getattr(transport, "get_json", None)):
        raise TypeError("effects_audit_transport_invalid")
    head_query = urlencode(
        {"state": "all", "head": f"desarrollo-via:{EXPECTED_HEAD}", "per_page": 100}
    )
    urls = {
        "head_prs": f"{API_BASE}/pulls?{head_query}",
        "commit_prs": f"{API_BASE}/commits/{EXPECTED_SHA}/pulls",
        "actions": f"{API_BASE}/actions/runs?head_sha={EXPECTED_SHA}&per_page=1",
        "checks": f"{API_BASE}/commits/{EXPECTED_SHA}/check-runs",
        "statuses": f"{API_BASE}/commits/{EXPECTED_SHA}/status",
    }
    payloads: dict[str, Any] = {}
    for label, url in urls.items():
        try:
            status, payload = transport.get_json(url)
        except EffectsAuditTransportError:
            raise
        except Exception as error:
            raise EffectsAuditTransportError(
                "effects_audit_transport_error"
            ) from error
        if status != 200:
            raise EffectsAuditTransportError(f"effects_audit_http_{status}")
        payloads[label] = payload
    return evaluate_effects_payloads(payloads)


def main() -> int:
    try:
        result = collect_effects_once(PublicJsonGetTransport())
    except (EffectsAuditInputError, EffectsAuditTransportError) as error:
        print(json.dumps({"decision": "NO-GO", "reason": str(error)}))
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.decision == "EFFECTS-ABSENT" else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EffectsAuditInputError",
    "EffectsAuditResult",
    "EffectsAuditTransportError",
    "PublicJsonGetTransport",
    "collect_effects_once",
    "evaluate_effects_payloads",
]
