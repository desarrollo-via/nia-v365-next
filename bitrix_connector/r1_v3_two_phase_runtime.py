"""Exact V3 composition, dormant until the two-phase controller starts."""
from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Callable
from .r1_integral_product_runtime import ExactR1SharedReviewRuntime, PersistentOneShotBearerSecretSink, build_integral_product_factory_binding
from .r1_result_eaor_coordinator import EAOR_ACCEPTANCE
from .r1_result_eaor_product_launcher import R1ResultEaorProductLauncher
from .r1_v3_two_phase_runner import R1V3SanitizedCheckpointStore, R1V3TwoPhaseRunner


def build_dormant_r1_v3_two_phase_runner(*, checkpoint_path: Path, ledger_path: Path, expected_deployed_sha: str, expected_deployed_tree: str, local_state_guard: Callable[[], bool], current_day: str | None = None) -> R1V3TwoPhaseRunner:
    if not callable(local_state_guard):
        raise TypeError("r1_v3_local_state_guard_invalid")
    shared = ExactR1SharedReviewRuntime(expected_deployed_sha=expected_deployed_sha, expected_deployed_tree=expected_deployed_tree)
    binding = build_integral_product_factory_binding(local_state_guard=local_state_guard, shared_review_runtime=shared, provisioning_sink=PersistentOneShotBearerSecretSink(ledger_path=ledger_path))
    runner = R1ResultEaorProductLauncher(current_day=current_day or date.today().isoformat()).build_runner_from_binding_once(acceptance=EAOR_ACCEPTANCE, binding=binding)
    return R1V3TwoPhaseRunner(runner=runner, checkpoint=R1V3SanitizedCheckpointStore(path=checkpoint_path))


__all__ = ["build_dormant_r1_v3_two_phase_runner"]
