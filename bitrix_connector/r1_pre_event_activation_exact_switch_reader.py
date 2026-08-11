"""Exact, non-enumerating reader for the three non-secret R1 switches."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Optional, Protocol

from .r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES,
    SWITCH_ORDER,
    SanitizedSwitchBaseline,
)


class ExactSwitchValueSource(Protocol):
    def read_exact_once(self, name: str) -> tuple[bool, Optional[str]]: ...

    def close(self) -> None: ...


class MappingExactSwitchValueSource:
    """Uses only exact subscription; it never iterates the supplied mapping."""

    __slots__ = ("_closed", "_mapping", "_used")

    def __init__(self, mapping: Mapping[str, str]) -> None:
        if mapping is None or not callable(getattr(mapping, "__getitem__", None)):
            raise TypeError("r1_exact_switch_mapping_invalid")
        self._mapping: Optional[Mapping[str, str]] = mapping
        self._used: set[str] = set()
        self._closed = False

    def read_exact_once(self, name: str) -> tuple[bool, Optional[str]]:
        mapping = self._mapping
        if (
            self._closed
            or mapping is None
            or name not in SWITCH_ORDER
            or name in self._used
        ):
            raise RuntimeError("r1_exact_switch_read_blocked")
        self._used.add(name)
        try:
            value = mapping[name]
        except KeyError:
            return False, None
        if type(value) is not str:
            raise ValueError("r1_exact_switch_value_invalid")
        return True, value

    def close(self) -> None:
        self._mapping = None
        self._closed = True

    @property
    def exact_reads(self) -> tuple[str, ...]:
        return tuple(name for name in SWITCH_ORDER if name in self._used)


class ExactSwitchBaselineProbe:
    """One-shot collector compatible with the sanitized evidence collector."""

    __slots__ = ("_source", "_used")

    def __init__(self, *, source: ExactSwitchValueSource) -> None:
        if (
            source is None
            or not callable(getattr(source, "read_exact_once", None))
            or not callable(getattr(source, "close", None))
        ):
            raise TypeError("r1_exact_switch_source_invalid")
        self._source: Optional[ExactSwitchValueSource] = source
        self._used = False

    async def collect(
        self, *, names: tuple[str, ...]
    ) -> tuple[SanitizedSwitchBaseline, ...]:
        source, self._source = self._source, None
        if self._used or source is None or names != SWITCH_ORDER:
            self._used = True
            raise RuntimeError("r1_exact_switch_probe_reuse_or_scope_invalid")
        self._used = True
        result: list[SanitizedSwitchBaseline] = []
        close_failed = False
        try:
            for name in SWITCH_ORDER:
                present, value = source.read_exact_once(name)
                if present:
                    if value != EXPECTED_BASELINE_VALUES[name]:
                        raise ValueError("r1_exact_switch_baseline_invalid")
                elif value is not None:
                    raise ValueError("r1_exact_switch_absence_invalid")
                result.append(
                    SanitizedSwitchBaseline(
                        name=name,
                        present=present,
                        value=value,
                    )
                )
        finally:
            try:
                source.close()
            except BaseException:
                close_failed = True
        if close_failed:
            raise RuntimeError("r1_exact_switch_source_close_failed")
        return tuple(result)


__all__ = [
    "ExactSwitchBaselineProbe",
    "ExactSwitchValueSource",
    "MappingExactSwitchValueSource",
]
