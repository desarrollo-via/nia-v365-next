"""Owner M86-AI one-shot para la sonda agregada autorizada."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Literal

from .bitrix_history_r0_m84_windows_credential_backend import MAX_M84_BLOB_BYTES
from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)
from .bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    build_m86ae_dormant_windows_environment_source,
)
from .bitrix_history_r0_m86_environment_probe_authorization import (
    M86AFAuthorizationContract,
)


ProbeResult = Literal["FIT", "NO-GO"]
SourceFactory = Callable[[], M86AEDormantWindowsEnvironmentSource]


def _zeroize_buffers(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


class M86AIEnvironmentProbeOwner:
    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used = False

    def run_once(
        self,
        *,
        confirm_code: str,
        source_factory: SourceFactory,
    ) -> ProbeResult:
        if self._used:
            raise RuntimeError("m86ai_owner_already_used")
        self._used = True
        if not M86AFAuthorizationContract().accepts(confirm_code):
            return "NO-GO"

        source = None
        buffers: object = {}
        blob_owner = None
        blob = bytearray()
        result: ProbeResult = "NO-GO"
        cleanup_ok = True
        try:
            source = source_factory()
            if type(source) is not M86AEDormantWindowsEnvironmentSource:
                raise TypeError("m86ai_source_invalid")
            source.open_once()
            buffers = source.take_buffers_once()
            blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
            blob = blob_owner.take_blob_once()
            if 0 < len(blob) <= MAX_M84_BLOB_BYTES:
                result = "FIT"
        except BaseException:
            result = "NO-GO"
        finally:
            if blob:
                blob[:] = b"\x00" * len(blob)
            try:
                if blob_owner is not None:
                    blob_owner.close()
            except BaseException:
                cleanup_ok = False
            _zeroize_buffers(buffers)
            try:
                if source is not None:
                    source.close()
            except BaseException:
                cleanup_ok = False
        return result if cleanup_ok else "NO-GO"


def main(
    argv: Sequence[str] | None = None,
    *,
    source_factory: SourceFactory = build_m86ae_dormant_windows_environment_source,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    confirm_code = args[1] if len(args) == 2 and args[0] == "--confirm-code" else ""
    result = M86AIEnvironmentProbeOwner().run_once(
        confirm_code=confirm_code,
        source_factory=source_factory,
    )
    print(result)
    return 0 if result == "FIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["M86AIEnvironmentProbeOwner", "main"]
