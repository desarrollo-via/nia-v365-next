"""Entrypoint fixture-only del helper protegido R0."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict

from .bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedHelperState,
    ProtectedValueView,
    execute_protected_helper_once,
)


PROTECTED_HELPER_FIXTURE_CONFIRMATION = (
    "VALIDAR HELPER R0 SOLO CON VALORES FICTICIOS"
)


class _FixtureProtectedSource:
    """Fuente cerrada de ensayo; no conoce archivos ni almacenes reales."""

    def __init__(self) -> None:
        self._opened = False

    async def open(self) -> None:
        if self._opened:
            raise RuntimeError("protected_helper_fixture_reused")
        self._opened = True

    async def read(self, name: str) -> bytearray:
        if not self._opened or name not in PROTECTED_SETTING_NAMES:
            raise RuntimeError("protected_helper_fixture_read_blocked")
        position = PROTECTED_SETTING_NAMES.index(name) + 1
        return bytearray(f"fictional-value-{position}", "utf-8")

    async def close(self) -> None:
        self._opened = False


async def _fixture_operation(values: ProtectedValueView) -> None:
    for name in PROTECTED_SETTING_NAMES:
        if not values.read_text(name):
            raise RuntimeError("protected_helper_fixture_value_missing")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida el helper protegido sólo con una fuente ficticia.",
    )
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=(PROTECTED_HELPER_FIXTURE_CONFIRMATION,),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _parser().parse_args(argv)
    snapshot = asyncio.run(
        execute_protected_helper_once(
            source=_FixtureProtectedSource(),
            operation=_fixture_operation,
        )
    )
    print(json.dumps(asdict(snapshot), sort_keys=True))
    return 0 if snapshot.state is ProtectedHelperState.READY else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["PROTECTED_HELPER_FIXTURE_CONFIRMATION", "main"]
