"""Puente M86-BC fixture-only desde dotenv inyectado hasta el owner categórico."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from .bitrix_history_r0_m86_owned_buffer_provisioning import (
    M86AZInjectedOwnedBufferProvider,
    M86AZOwnedBufferProvisioningSource,
)
from .bitrix_history_r0_m86_dotenv_probe_authorization import (
    M86BD_PUBLIC_CATEGORIES,
    M86BDAuthorizationContract,
)
from .bitrix_history_r0_m86_stage_specific_real_owner import (
    M86AVCategory,
    M86AVStageSpecificRealOwner,
)
from .bitrix_history_r0_protected_dotenv_source import AllowlistedDotenvSource
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


def _zeroize(buffers: object) -> None:
    if type(buffers) is not dict:
        return
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)
    buffers.clear()


@dataclass(frozen=True)
class M86BCFixtureDotenvBridgeSnapshot:
    phase: Literal["M86-BC"] = "M86-BC"
    state: Literal["FIT", "NO-GO"] = "NO-GO"
    failure_category: M86AVCategory = "composition_failed"
    fixture_source_injected: Literal[True] = True
    real_dotenv_path_bound: Literal[False] = False
    aggregate_transferred: bool = False
    source_closed: bool = False
    values_exposed: Literal[False] = False
    immutable_text_created: Literal[False] = False
    cli_available: Literal[False] = False
    external_calls: Literal[0] = 0
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86BCFixtureDotenvBridgeOwner:
    __slots__ = ("_used",)

    def __init__(self) -> None:
        self._used = False

    async def run_once(
        self,
        *,
        source: AllowlistedDotenvSource,
        confirm_code: str,
    ) -> M86BCFixtureDotenvBridgeSnapshot:
        if self._used or type(source) is not AllowlistedDotenvSource:
            self._used = True
            raise RuntimeError("m86bc_owner_reuse_or_source_invalid")
        self._used = True

        authorization = M86BDAuthorizationContract()
        if not authorization.accepts(confirm_code):
            closed = await self._close_source(source)
            return M86BCFixtureDotenvBridgeSnapshot(
                failure_category=(
                    "authorization_invalid" if closed else "cleanup_ambiguous"
                ),
                source_closed=closed,
            )

        buffers: object = {}
        aggregate_transferred = False
        category: M86AVCategory = "source_open_unavailable"
        try:
            try:
                await source.open()
            except BaseException:
                category = "source_open_unavailable"
            else:
                try:
                    incoming: dict[str, bytearray] = {}
                    for name in PROTECTED_SETTING_NAMES:
                        value = await source.read(name)
                        if type(value) is not bytearray or not value or b"\x00" in value:
                            if type(value) is bytearray:
                                value[:] = b"\x00" * len(value)
                            raise ValueError("m86bc_value_invalid")
                        incoming[name] = value
                    buffers, incoming = incoming, {}
                    aggregate_transferred = True
                except BaseException:
                    _zeroize(locals().get("incoming"))
                    category = "source_transfer_unavailable"

            closed = await self._close_source(source)
            if not closed:
                category = "cleanup_ambiguous"
            if not aggregate_transferred or not closed:
                return M86BCFixtureDotenvBridgeSnapshot(
                    failure_category=category,
                    aggregate_transferred=aggregate_transferred,
                    source_closed=closed,
                )

            provider = M86AZInjectedOwnedBufferProvider(
                buffers=cast(dict[str, bytearray], buffers)
            )
            provisioned_source = M86AZOwnedBufferProvisioningSource(provider=provider)
            buffers = {}
            result = M86AVStageSpecificRealOwner(
                source_factory=lambda: provisioned_source,
                authorization_validator=authorization.accepts,
            ).run_once(confirm_code=confirm_code)
            failure_category: M86AVCategory = result.failure_category
            if (
                failure_category != "none"
                and failure_category not in M86BD_PUBLIC_CATEGORIES
            ):
                failure_category = "composition_failed"
            return M86BCFixtureDotenvBridgeSnapshot(
                state=result.state,
                failure_category=failure_category,
                aggregate_transferred=True,
                source_closed=True,
            )
        finally:
            _zeroize(buffers)

    @staticmethod
    async def _close_source(source: AllowlistedDotenvSource) -> bool:
        try:
            await source.close()
        except BaseException:
            return False
        return True


@dataclass(frozen=True)
class M86BCFixtureDotenvBridgeContract:
    phase: Literal["M86-BC"] = "M86-BC"
    state: Literal["FIXTURE-ONLY-INERT"] = "FIXTURE-ONLY-INERT"
    source_must_be_injected: Literal[True] = True
    real_path_factory_present: Literal[False] = False
    direct_bytearray_transfer: Literal[True] = True
    exact_authorization_phase: Literal["M86-BD"] = "M86-BD"
    legacy_authorization_accepted: Literal[False] = False
    immutable_text_handoff_allowed: Literal[False] = False
    exact_name_budget: Literal[7] = 7
    enumeration_budget: Literal[0] = 0
    fallback_budget: Literal[0] = 0
    cli_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0


__all__ = [
    "M86BCFixtureDotenvBridgeContract",
    "M86BCFixtureDotenvBridgeOwner",
    "M86BCFixtureDotenvBridgeSnapshot",
]
