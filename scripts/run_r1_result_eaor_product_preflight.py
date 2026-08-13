"""CLI for the local-only, inert EAOR product launcher preflight."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from bitrix_connector.r1_result_eaor_product_launcher import (
    INERT_PREFLIGHT_CONFIRMATION,
    R1ResultEaorProductLauncher,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=(INERT_PREFLIGHT_CONFIRMATION,),
    )
    return parser


def main(argv=None, *, launcher_factory=R1ResultEaorProductLauncher) -> int:
    args = _parser().parse_args(argv)
    launcher = launcher_factory()
    result = launcher.preflight_once(confirmation=args.confirm_code)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.state in {
        "READY-EXTERNAL-PREFLIGHT", "READY-CONTRACT-REFRESH"
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
