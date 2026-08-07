"""Allowlist local congelada del corte M53-M86.

Los patrones sólo facilitan la resolución. La huella del conjunto ordenado
impide aceptar silenciosamente rutas nuevas, ausentes o ajenas al corte.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Literal


M53_M86_CUT_PHASE: Literal["M86-CH"] = "M86-CH"
M53_M86_CUT_EXPECTED_COUNT = 284
M53_M86_CUT_EXPECTED_SHA256 = (
    "67d51eea072c40f7d2a88cc2615809c75224aa40502e2a22bf780ed291ab3dc6"
)

M53_M86_CUT_PATTERNS = (
    "bitrix_connector/bitrix_history_r0_*.py",
    "bitrix_connector/bitrix_event_scoped_*.py",
    "bitrix_connector/bitrix_webhook_event_roundtrip.py",
    "bitrix_connector/event_scoped_oauth.py",
    "bitrix_connector/bitrix_oauth_refresh_execution_owner.py",
    "bitrix_connector/bitrix_oauth_refresh_rollback_readiness.py",
    "bitrix_connector/__init__.py",
    "bitrix_connector/bot_v2_preflight.py",
    "bitrix_connector/g0_entrypoint.py",
    "bitrix_connector/openline_pilot_preflight.py",
    "bitrix_connector/router.py",
    "bitrix_connector/webhook_handler.py",
    "tests/test_bitrix_history_r0_*.py",
    "tests/test_bitrix_event_scoped_*.py",
    "tests/test_bitrix_webhook_event_roundtrip.py",
    "tests/test_bitrix_oauth_refresh_execution_owner.py",
    "tests/test_bitrix_oauth_refresh_rollback_readiness.py",
    "tests/test_bitrix_g0_entrypoint.py",
    "tests/test_bitrix_openline_pilot_preflight.py",
    "docs/bitrix_event_scoped_r1_deployment_contract.md",
    "docs/bitrix_history_r0_preflight_execution_runbook.md",
    "docs/bitrix_p1b_protected_settings_runbook.md",
    "scripts/lanzar_bitrix_history_r0_m38_oculto.ps1",
)

M53_M86_FORBIDDEN_PARTS = frozenset(
    {
        ".env",
        ".git",
        ".venv",
        "__pycache__",
        ".runtime",
        "logs",
    }
)


@dataclass(frozen=True)
class M53M86CutAudit:
    phase: Literal["M86-CH"] = M53_M86_CUT_PHASE
    state: Literal["FROZEN", "NO-GO"] = "NO-GO"
    dependency_cut_frozen: bool = False
    resolved_count: int = 0
    candidate_count: int = 0
    implementation_count: int = 0
    test_count: int = 0
    documentation_count: int = 0
    script_count: int = 0
    missing_or_extra_count: int = 0
    forbidden_count: int = 0
    index_writes: Literal[0] = 0
    external_calls: Literal[0] = 0


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def resolve_m53_m86_cut_paths(project_root: Path) -> tuple[str, ...]:
    root = project_root.resolve(strict=True)
    resolved = {
        _relative_posix(root, path.resolve(strict=True))
        for pattern in M53_M86_CUT_PATTERNS
        for path in root.glob(pattern)
        if path.is_file()
    }
    return tuple(sorted(resolved))


def m53_m86_cut_digest(paths: Iterable[str]) -> str:
    normalized = tuple(sorted(set(paths)))
    payload = "\n".join(normalized).encode("utf-8")
    return sha256(payload).hexdigest()


def audit_m53_m86_cut(
    project_root: Path,
    *,
    candidate_paths: Iterable[str],
) -> M53M86CutAudit:
    resolved = resolve_m53_m86_cut_paths(project_root)
    candidates = tuple(sorted(set(candidate_paths)))
    resolved_set = set(resolved)
    candidate_set = set(candidates)
    forbidden = tuple(
        path
        for path in resolved
        if M53_M86_FORBIDDEN_PARTS.intersection(Path(path).parts)
    )
    symmetric_difference = resolved_set.symmetric_difference(candidate_set)
    frozen = bool(
        len(resolved) == M53_M86_CUT_EXPECTED_COUNT
        and m53_m86_cut_digest(resolved) == M53_M86_CUT_EXPECTED_SHA256
        and not forbidden
        and not symmetric_difference
    )
    return M53M86CutAudit(
        state="FROZEN" if frozen else "NO-GO",
        dependency_cut_frozen=frozen,
        resolved_count=len(resolved),
        candidate_count=len(candidates),
        implementation_count=sum(path.startswith("bitrix_connector/") for path in resolved),
        test_count=sum(path.startswith("tests/") for path in resolved),
        documentation_count=sum(path.startswith("docs/") for path in resolved),
        script_count=sum(path.startswith("scripts/") for path in resolved),
        missing_or_extra_count=len(symmetric_difference),
        forbidden_count=len(forbidden),
    )


__all__ = [
    "M53M86CutAudit",
    "M53_M86_CUT_EXPECTED_COUNT",
    "M53_M86_CUT_EXPECTED_SHA256",
    "M53_M86_CUT_PATTERNS",
    "audit_m53_m86_cut",
    "m53_m86_cut_digest",
    "resolve_m53_m86_cut_paths",
]
