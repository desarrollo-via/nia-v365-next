"""Run unittest discovery against an extracted tree under Python isolated mode."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import unittest


def _contained_directory(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("start_directory_outside_root")
    if not candidate.is_dir():
        raise ValueError("start_directory_missing")
    return candidate


def run(root_value: str, start_value: str, pattern: str, quiet: bool) -> int:
    root = Path(root_value).resolve()
    if not root.is_dir():
        raise ValueError("root_directory_missing")

    start = _contained_directory(root, start_value)
    sys.path.insert(0, str(root))
    os.chdir(root)

    suite = unittest.TestLoader().discover(str(start), pattern=pattern)
    count = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=0 if quiet else 1).run(suite)
    status = "PASS" if result.wasSuccessful() else "FAIL"
    print(
        "ISOLATED-UNITTEST-{} tests={} failures={} errors={} skipped={}".format(
            status,
            count,
            len(result.failures),
            len(result.errors),
            len(result.skipped),
        )
    )
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--start", default="tests")
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        return run(args.root, args.start, args.pattern, args.quiet)
    except (OSError, ValueError) as exc:
        print(f"ISOLATED-UNITTEST-ERROR reason={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
