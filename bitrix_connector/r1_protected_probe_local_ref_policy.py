"""Pure policy for local refs created by candidate publication and rollback."""

from __future__ import annotations

import re
from enum import Enum
from typing import Mapping


_SHA = re.compile(r"[0-9a-f]{40}")


class LocalRefPhase(str, Enum):
    PUBLISHED = "published"
    ROLLED_BACK = "rolled_back"


class LocalRefDecision(str, Enum):
    EXACT_WITHOUT_TRACKING = "exact_without_tracking"
    EXACT_WITH_TRACKING = "exact_with_tracking"
    EXACT_RESTORED = "exact_restored"
    BASELINE_INVALID = "baseline_invalid"
    REF_DRIFT = "ref_drift"


def _validated_snapshot(refs: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(refs, Mapping):
        raise TypeError("local_ref_snapshot_mapping_required")
    snapshot: dict[str, str] = {}
    for name, sha in refs.items():
        if type(name) is not str or not name.startswith("refs/"):
            raise ValueError("local_ref_name_invalid")
        if type(sha) is not str or _SHA.fullmatch(sha) is None:
            raise ValueError("local_ref_sha_invalid")
        snapshot[name] = sha
    if len(snapshot) != len(refs):
        raise ValueError("local_ref_name_duplicate")
    return snapshot


def evaluate_local_ref_transition(
    *,
    before: Mapping[str, str],
    after: Mapping[str, str],
    branch: str,
    candidate_sha: str,
    phase: LocalRefPhase,
) -> LocalRefDecision:
    """Allow only the exact origin tracking ref, then literal restoration."""

    if (
        type(branch) is not str
        or not branch
        or branch.startswith("/")
        or branch.endswith("/")
        or ".." in branch
        or branch.startswith("refs/")
    ):
        raise ValueError("candidate_branch_invalid")
    if type(candidate_sha) is not str or _SHA.fullmatch(candidate_sha) is None:
        raise ValueError("candidate_sha_invalid")
    if not isinstance(phase, LocalRefPhase):
        raise TypeError("local_ref_phase_invalid")

    baseline = _validated_snapshot(before)
    current = _validated_snapshot(after)
    own_ref = f"refs/heads/{branch}"
    tracking_ref = f"refs/remotes/origin/{branch}"

    if own_ref in baseline or tracking_ref in baseline:
        return LocalRefDecision.BASELINE_INVALID

    if phase is LocalRefPhase.ROLLED_BACK:
        if current == baseline:
            return LocalRefDecision.EXACT_RESTORED
        return LocalRefDecision.REF_DRIFT

    if current == baseline:
        return LocalRefDecision.EXACT_WITHOUT_TRACKING

    expected_with_tracking = dict(baseline)
    expected_with_tracking[tracking_ref] = candidate_sha
    if current == expected_with_tracking:
        return LocalRefDecision.EXACT_WITH_TRACKING
    return LocalRefDecision.REF_DRIFT


__all__ = [
    "LocalRefDecision",
    "LocalRefPhase",
    "evaluate_local_ref_transition",
]
