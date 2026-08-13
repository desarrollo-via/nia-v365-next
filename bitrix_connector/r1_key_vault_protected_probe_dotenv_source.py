"""Exact one-value dotenv source for the protected R1 probe invocation."""

from __future__ import annotations

import stat
from pathlib import Path

from .r1_key_vault_protected_probe_invocation_owner import REVIEW_TOKEN_NAME


MAX_DOTENV_BYTES = 64 * 1024
EXPECTED_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
_NAME = REVIEW_TOKEN_NAME.encode("ascii")


def _clear(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)
        value.clear()


class ExactReviewTokenDotenvSource:
    """Reads one exact name once; never returns other dotenv entries."""

    kind = "protected-review-token-dotenv"
    __slots__ = ("_buffer", "_expected_path", "_opened", "_path", "_used")

    def __init__(
        self,
        path: Path,
        *,
        expected_path: Path = EXPECTED_DOTENV_PATH,
    ) -> None:
        self._path = Path(path)
        self._expected_path = Path(expected_path)
        self._buffer = bytearray()
        self._opened = False
        self._used = False

    def __repr__(self) -> str:
        return "ExactReviewTokenDotenvSource(<redacted>)"

    async def open(self) -> None:
        if self._used:
            raise RuntimeError("r1_probe_dotenv_source_reused")
        self._used = True
        candidate = self._path.resolve(strict=False)
        expected = self._expected_path.resolve(strict=False)
        if candidate != expected or self._path.is_symlink():
            raise ValueError("r1_probe_dotenv_path_invalid")
        metadata = self._path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > MAX_DOTENV_BYTES
        ):
            raise ValueError("r1_probe_dotenv_file_invalid")

        selected = bytearray()
        matches = 0
        total = 0
        try:
            with self._path.open("rb") as stream:
                for raw_line in stream:
                    total += len(raw_line)
                    if total > MAX_DOTENV_BYTES:
                        raise ValueError("r1_probe_dotenv_file_too_large")
                    line = raw_line.rstrip(b"\r\n")
                    if not line or line.lstrip().startswith(b"#") or b"=" not in line:
                        continue
                    raw_name, raw_value = line.split(b"=", 1)
                    if raw_name.strip() != _NAME:
                        continue
                    matches += 1
                    if matches != 1:
                        raise ValueError("r1_probe_dotenv_duplicate_name")
                    if (
                        raw_value != raw_value.strip()
                        or raw_value[:1] in {b"'", b'"'}
                        or raw_value[-1:] in {b"'", b'"'}
                        or not 24 <= len(raw_value) <= 4096
                        or any(byte < 33 or byte == 127 for byte in raw_value)
                    ):
                        raise ValueError("r1_probe_dotenv_token_invalid")
                    try:
                        raw_value.decode("utf-8")
                    except UnicodeDecodeError:
                        raise ValueError("r1_probe_dotenv_token_invalid") from None
                    selected = bytearray(raw_value)
            if matches != 1:
                raise ValueError("r1_probe_dotenv_token_unavailable")
        except BaseException:
            _clear(selected)
            raise
        self._buffer = selected
        self._opened = True

    async def read_exact(self, name: str) -> bytearray:
        if not self._opened or name != REVIEW_TOKEN_NAME or not self._buffer:
            raise RuntimeError("r1_probe_dotenv_read_blocked")
        value, self._buffer = self._buffer, bytearray()
        return value

    async def close(self) -> None:
        _clear(self._buffer)
        self._opened = False


__all__ = [
    "EXPECTED_DOTENV_PATH",
    "ExactReviewTokenDotenvSource",
    "MAX_DOTENV_BYTES",
]
