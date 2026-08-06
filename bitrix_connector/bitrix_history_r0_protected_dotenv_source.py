"""Fuente dotenv allowlisted, one-shot y sin expansión de valores."""

from __future__ import annotations

import stat
from pathlib import Path

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


MAX_PROTECTED_DOTENV_BYTES = 64 * 1024
_ALLOWED_NAMES = {
    name.encode("ascii"): name for name in PROTECTED_SETTING_NAMES
}


def _zeroize(buffers: dict[str, bytearray]) -> None:
    for value in buffers.values():
        value[:] = b"\x00" * len(value)
    buffers.clear()


def _normalize_value(raw_value: bytes) -> bytearray:
    value = raw_value.strip()
    if not value or b"\x00" in value:
        raise ValueError("protected_dotenv_value_invalid")
    starts_quoted = value[:1] in {b"'", b'"'}
    ends_quoted = value[-1:] in {b"'", b'"'}
    if starts_quoted or ends_quoted:
        if len(value) < 2 or value[:1] != value[-1:]:
            raise ValueError("protected_dotenv_quote_invalid")
        value = value[1:-1]
    if not value:
        raise ValueError("protected_dotenv_value_invalid")
    return bytearray(value)


class AllowlistedDotenvSource:
    """Extrae sólo siete nombres aprobados desde una ruta autorizada externa."""

    __slots__ = ("_buffers", "_opened", "_path", "_used")

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._buffers: dict[str, bytearray] = {}
        self._opened = False
        self._used = False

    async def open(self) -> None:
        if self._used:
            raise RuntimeError("protected_dotenv_source_reused")
        self._used = True
        parsed: dict[str, bytearray] = {}
        try:
            if self._path.is_symlink():
                raise ValueError("protected_dotenv_symlink_blocked")
            metadata = self._path.stat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size <= 0
                or metadata.st_size > MAX_PROTECTED_DOTENV_BYTES
            ):
                raise ValueError("protected_dotenv_file_invalid")

            total_bytes = 0
            with self._path.open("rb") as stream:
                for raw_line in stream:
                    total_bytes += len(raw_line)
                    if total_bytes > MAX_PROTECTED_DOTENV_BYTES:
                        raise ValueError("protected_dotenv_file_too_large")
                    line = raw_line.strip()
                    if not line or line.startswith(b"#"):
                        continue
                    if line.startswith(b"export "):
                        line = line[7:].lstrip()
                    if b"=" not in line:
                        raise ValueError("protected_dotenv_line_invalid")
                    raw_name, raw_value = line.split(b"=", 1)
                    name = _ALLOWED_NAMES.get(raw_name.strip())
                    if name is None:
                        continue
                    if name in parsed:
                        raise ValueError("protected_dotenv_duplicate_name")
                    parsed[name] = _normalize_value(raw_value)
        except Exception:
            _zeroize(parsed)
            raise

        self._buffers = parsed
        self._opened = True

    async def read(self, name: str) -> bytearray:
        if not self._opened or name not in PROTECTED_SETTING_NAMES:
            raise RuntimeError("protected_dotenv_read_blocked")
        return self._buffers.pop(name, bytearray())

    async def close(self) -> None:
        _zeroize(self._buffers)
        self._opened = False

    def __repr__(self) -> str:
        return "AllowlistedDotenvSource(<redacted>)"


__all__ = ["AllowlistedDotenvSource", "MAX_PROTECTED_DOTENV_BYTES"]
