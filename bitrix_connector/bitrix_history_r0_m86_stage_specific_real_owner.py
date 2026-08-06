"""Owner M86-AV one-shot por etapa, real-ready y sin CLI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from .bitrix_history_r0_m84_windows_credential_backend import MAX_M84_BLOB_BYTES
from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)
from .bitrix_history_r0_m86_dormant_windows_environment_binding import (
    M86AEDormantWindowsEnvironmentSource,
    build_m86ae_dormant_windows_environment_source,
)
from .bitrix_history_r0_m86_owned_buffer_provisioning import (
    M86AZOwnedBufferProvisioningSource,
)
from .bitrix_history_r0_m86_stage_specific_probe_authorization import (
    M86AU_PUBLIC_CATEGORIES,
    M86AUAuthorizationContract,
)


M86AVCategory = Literal[
    "none",
    "authorization_invalid",
    "source_factory_unavailable",
    "source_open_unavailable",
    "source_transfer_unavailable",
    "candidate_not_fit",
    "composition_failed",
    "cleanup_ambiguous",
]
M86AVSource = M86AEDormantWindowsEnvironmentSource | M86AZOwnedBufferProvisioningSource
SourceFactory = Callable[[], M86AVSource]
AuthorizationValidator = Callable[[str], bool]


def _zeroize_buffers(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


@dataclass(frozen=True)
class M86AVPublicDiagnostic:
    phase: Literal["M86-AV"] = "M86-AV"
    state: Literal["FIT", "NO-GO"] = "NO-GO"
    failure_category: M86AVCategory = "composition_failed"
    individual_key_disclosed: Literal[False] = False
    value_disclosed: Literal[False] = False
    length_disclosed: Literal[False] = False
    progress_count_disclosed: Literal[False] = False
    source_read_calls_disclosed: Literal[False] = False
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


def _build_diagnostic(category: M86AVCategory) -> M86AVPublicDiagnostic:
    if category == "none":
        return M86AVPublicDiagnostic(state="FIT", failure_category="none")
    if category not in M86AU_PUBLIC_CATEGORIES:
        category = "composition_failed"
    return M86AVPublicDiagnostic(failure_category=cast(M86AVCategory, category))


@dataclass(frozen=True)
class M86AVDormantPreview:
    phase: Literal["M86-AV"] = "M86-AV"
    state: Literal["DORMANT-WAITING-EXACT-AUTHORIZATION"] = (
        "DORMANT-WAITING-EXACT-AUTHORIZATION"
    )
    real_factory_bound: Literal[True] = True
    real_factory_called: Literal[False] = False
    execution_surface_one_shot: Literal[True] = True
    execution_surface_has_cli: Literal[False] = False
    authorization_received: Literal[False] = False
    current_real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0


class M86AVStageSpecificRealOwner:
    __slots__ = ("_authorization_validator", "_source_factory", "_used")

    def __init__(
        self,
        *,
        source_factory: SourceFactory = build_m86ae_dormant_windows_environment_source,
        authorization_validator: AuthorizationValidator | None = None,
    ) -> None:
        if not callable(source_factory):
            raise TypeError("m86av_source_factory_invalid")
        if authorization_validator is None:
            authorization_validator = M86AUAuthorizationContract().accepts
        if not callable(authorization_validator):
            raise TypeError("m86av_authorization_validator_invalid")
        self._source_factory = source_factory
        self._authorization_validator = authorization_validator
        self._used = False

    def preview(self) -> M86AVDormantPreview:
        return M86AVDormantPreview()

    def run_once(self, *, confirm_code: str) -> M86AVPublicDiagnostic:
        if self._used:
            raise RuntimeError("m86av_owner_already_used")
        self._used = True
        try:
            authorized = self._authorization_validator(confirm_code)
        except BaseException:
            authorized = False
        if authorized is not True:
            return _build_diagnostic("authorization_invalid")

        source = None
        buffers: object = {}
        blob_owner = None
        blob = bytearray()
        category: M86AVCategory = "source_factory_unavailable"
        cleanup_ok = True
        try:
            try:
                source = self._source_factory()
                if type(source) not in (
                    M86AEDormantWindowsEnvironmentSource,
                    M86AZOwnedBufferProvisioningSource,
                ):
                    raise TypeError("m86av_source_invalid")
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
                    except BaseException:
                        category = "source_transfer_unavailable"
                    else:
                        try:
                            blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
                            blob = blob_owner.take_blob_once()
                            category = (
                                "none"
                                if 0 < len(blob) <= MAX_M84_BLOB_BYTES
                                else "candidate_not_fit"
                            )
                        except ValueError:
                            category = "candidate_not_fit"
                        except BaseException:
                            category = "composition_failed"
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
        if not cleanup_ok:
            category = "cleanup_ambiguous"
        return _build_diagnostic(category)


__all__ = [
    "M86AVDormantPreview",
    "M86AVPublicDiagnostic",
    "M86AVStageSpecificRealOwner",
]
