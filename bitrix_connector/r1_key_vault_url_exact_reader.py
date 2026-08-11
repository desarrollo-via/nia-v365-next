"""Dormant one-shot reader for the exact non-secret Key Vault URL setting."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional, Protocol


KEY_VAULT_URL_SETTING_NAME = "NIA_BITRIX_KEY_VAULT_URL"
_EXACT_VAULT_URL = re.compile(
    r"https://[a-z0-9](?:[a-z0-9-]{1,22}[a-z0-9])?\.vault\.azure\.net"
)


@dataclass(frozen=True)
class SanitizedKeyVaultUrlBaseline:
    name: str
    present: bool
    value: Optional[str]


class ExactKeyVaultUrlValueSource(Protocol):
    def read_exact_once(self, name: str) -> tuple[bool, Optional[str]]: ...

    def close(self) -> None: ...


class MappingExactKeyVaultUrlValueSource:
    """Uses exact subscription only and never iterates the host mapping."""

    __slots__ = ("_closed", "_mapping", "_used")

    def __init__(self, mapping: Mapping[str, str]) -> None:
        if mapping is None or not callable(getattr(mapping, "__getitem__", None)):
            raise TypeError("r1_key_vault_url_mapping_invalid")
        self._mapping: Optional[Mapping[str, str]] = mapping
        self._used = False
        self._closed = False

    def read_exact_once(self, name: str) -> tuple[bool, Optional[str]]:
        mapping = self._mapping
        if (
            self._closed
            or self._used
            or mapping is None
            or name != KEY_VAULT_URL_SETTING_NAME
        ):
            self._used = True
            raise RuntimeError("r1_key_vault_url_read_blocked")
        self._used = True
        try:
            value = mapping[name]
        except KeyError:
            return False, None
        if type(value) is not str:
            raise ValueError("r1_key_vault_url_value_invalid")
        return True, value

    def close(self) -> None:
        self._mapping = None
        self._closed = True

    @property
    def exact_reads(self) -> int:
        return int(self._used)


class ExactKeyVaultUrlBaselineProbe:
    """Reads nothing until collect() receives the one exact setting name."""

    __slots__ = ("_source", "_used")

    def __init__(self, *, source: ExactKeyVaultUrlValueSource) -> None:
        if (
            source is None
            or not callable(getattr(source, "read_exact_once", None))
            or not callable(getattr(source, "close", None))
        ):
            raise TypeError("r1_key_vault_url_source_invalid")
        self._source: Optional[ExactKeyVaultUrlValueSource] = source
        self._used = False

    def collect(self, *, name: str) -> SanitizedKeyVaultUrlBaseline:
        source, self._source = self._source, None
        if self._used or source is None or name != KEY_VAULT_URL_SETTING_NAME:
            self._used = True
            raise RuntimeError("r1_key_vault_url_probe_reuse_or_scope_invalid")
        self._used = True
        close_failed = False
        try:
            present, value = source.read_exact_once(name)
            if present:
                if type(value) is not str or _EXACT_VAULT_URL.fullmatch(value) is None:
                    raise ValueError("r1_key_vault_url_baseline_invalid")
            elif value is not None:
                raise ValueError("r1_key_vault_url_absence_invalid")
            return SanitizedKeyVaultUrlBaseline(
                name=name,
                present=present,
                value=value,
            )
        finally:
            try:
                source.close()
            except BaseException:
                close_failed = True
            if close_failed:
                raise RuntimeError("r1_key_vault_url_source_close_failed")


__all__ = [
    "ExactKeyVaultUrlBaselineProbe",
    "ExactKeyVaultUrlValueSource",
    "KEY_VAULT_URL_SETTING_NAME",
    "MappingExactKeyVaultUrlValueSource",
    "SanitizedKeyVaultUrlBaseline",
]
