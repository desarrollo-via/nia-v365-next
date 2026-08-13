"""Plan literal e inerte de stage para el corte M53-M86."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Literal

from .bitrix_event_scoped_r1_cut_manifest import (
    audit_m53_m86_cut,
    resolve_m53_m86_cut_paths,
)


M53_M86_STAGE_PHASE: Literal["M86-CI"] = "M86-CI"
M53_M86_STAGE_ARGV_SHA256 = (
    "01b1f9ad64ee93269cebef5c6a148471472ce438665b2ec8638cfb90e5de674a"
)


@dataclass(frozen=True)
class M53M86StagePlan:
    phase: Literal["M86-CI"] = M53_M86_STAGE_PHASE
    state: Literal["PREPARED", "NO-GO"] = "NO-GO"
    argv: tuple[str, ...] = ()
    path_count: int = 0
    literal_paths_only: bool = False
    manifest_verified: bool = False
    index_unchanged: Literal[True] = True
    stage_authorized: Literal[False] = False
    executable: Literal[False] = False
    git_calls: Literal[0] = 0
    external_calls: Literal[0] = 0


def m53_m86_stage_argv_digest(argv: Iterable[str]) -> str:
    return sha256("\0".join(argv).encode("utf-8")).hexdigest()


def build_m53_m86_stage_plan(
    project_root: Path,
    *,
    candidate_paths: Iterable[str],
) -> M53M86StagePlan:
    candidates = tuple(candidate_paths)
    cut = audit_m53_m86_cut(project_root, candidate_paths=candidates)
    if not cut.dependency_cut_frozen:
        return M53M86StagePlan()

    paths = resolve_m53_m86_cut_paths(project_root)
    literal_only = bool(
        paths
        and all(path not in {".", "..", "-A", "--all"} for path in paths)
        and all(not any(marker in path for marker in ("*", "?", "[", "]")) for path in paths)
    )
    argv = ("git", "add", "--", *paths)
    if not literal_only or m53_m86_stage_argv_digest(argv) != M53_M86_STAGE_ARGV_SHA256:
        return M53M86StagePlan()

    return M53M86StagePlan(
        state="PREPARED",
        argv=argv,
        path_count=len(paths),
        literal_paths_only=True,
        manifest_verified=True,
    )


__all__ = [
    "M53M86StagePlan",
    "M53_M86_STAGE_ARGV_SHA256",
    "build_m53_m86_stage_plan",
    "m53_m86_stage_argv_digest",
]
