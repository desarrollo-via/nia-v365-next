"""Owner M86-AS exclusivo para dobles herméticos y sin binding real."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_m86_stage_specific_source_diagnostic import (
    M86ASStageSpecificSourceDiagnostic,
    build_m86as_source_diagnostic,
)


M86AS_FIXTURE_CONFIRMATION = "AUDITAR M86-AS SOLO CON DOBLES HERMETICOS"
FixtureSourceFactory = Callable[[], object]


def _zeroize_buffers(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


@dataclass(frozen=True)
class M86ASFixturePreview:
    phase: Literal["M86-AS"] = "M86-AS"
    state: Literal["FIXTURE-DORMANT"] = "FIXTURE-DORMANT"
    fixture_factory_bound: Literal[True] = True
    fixture_factory_called: Literal[False] = False
    real_source_bound: Literal[False] = False
    real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0


class M86ASStageSpecificFixtureOwner:
    __slots__ = ("_source_factory", "_used")

    def __init__(self, *, source_factory: FixtureSourceFactory) -> None:
        if not callable(source_factory):
            raise TypeError("m86as_fixture_factory_invalid")
        self._source_factory = source_factory
        self._used = False

    def preview(self) -> M86ASFixturePreview:
        return M86ASFixturePreview()

    def run_once(self, *, confirm_code: str) -> M86ASStageSpecificSourceDiagnostic:
        if self._used:
            raise RuntimeError("m86as_fixture_owner_already_used")
        self._used = True
        if type(confirm_code) is not str or confirm_code != M86AS_FIXTURE_CONFIRMATION:
            return build_m86as_source_diagnostic("authorization_invalid")

        source = None
        buffers: object = {}
        category = "source_factory_unavailable"
        cleanup_ok = True
        try:
            try:
                source = self._source_factory()
                if not callable(getattr(source, "open_once", None)) or not callable(
                    getattr(source, "take_buffers_once", None)
                ) or not callable(getattr(source, "close", None)):
                    raise TypeError("m86as_fixture_source_invalid")
            except BaseException:
                category = "source_factory_unavailable"
            else:
                try:
                    source.open_once()
                except BaseException:
                    category = "source_open_unavailable"
                else:
                    try:
                        buffers = source.take_buffers_once()
                        if type(buffers) is not dict:
                            raise TypeError("m86as_fixture_buffers_invalid")
                    except BaseException:
                        category = "source_transfer_unavailable"
                    else:
                        category = "none"
        finally:
            _zeroize_buffers(buffers)
            try:
                if source is not None and callable(getattr(source, "close", None)):
                    source.close()
            except BaseException:
                cleanup_ok = False
        if not cleanup_ok:
            category = "cleanup_ambiguous"
        return build_m86as_source_diagnostic(category)


__all__ = [
    "M86AS_FIXTURE_CONFIRMATION",
    "M86ASFixturePreview",
    "M86ASStageSpecificFixtureOwner",
]
