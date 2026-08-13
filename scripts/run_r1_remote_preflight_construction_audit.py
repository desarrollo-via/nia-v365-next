"""Audits only dormant construction of the 2026-08-13 remote-preflight EAOR."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from bitrix_connector.r1_result_eaor_remote_preflight_real_binding import (
    CONSTRUCTION_AUDIT_CONFIRMATION,
    build_dormant_real_remote_preflight_binding,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=(CONSTRUCTION_AUDIT_CONFIRMATION,),
    )
    return parser


def main(argv=None, *, binding_factory=build_dormant_real_remote_preflight_binding):
    _parser().parse_args(argv)
    binding = binding_factory(local_state_guard=lambda: True)
    coordinator = binding.build_coordinator_once()
    binding_preview = binding.preview()
    coordinator_preview = coordinator.preview()
    payload = {
        **asdict(binding_preview),
        "coordinator_state": coordinator_preview.state,
        "coordinator_acceptance_calls": coordinator_preview.acceptance_calls,
        "coordinator_diagnostic_constructions": (
            coordinator_preview.diagnostic_constructions
        ),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if (
        binding_preview.state == "BOUND-DORMANT"
        and coordinator_preview.state == "INERT"
        and not binding_preview.execution_authorized
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
