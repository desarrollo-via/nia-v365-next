"""Composición M70 hermética de senders one-shot creados por fábricas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_client import BitrixClientResult
from .bitrix_history_r0_isolated_roundtrip import (
    InjectedBitrixSender,
    InjectedNiaSender,
)
from .bitrix_history_r0_m68_combined_preflight import CombinedR1PreflightAdapter
from .bitrix_history_r0_m69_post_anchor_bridge import (
    InjectedPostAnchorHistoryReader,
    PostAnchorBridgeStatus,
    PostAnchorExactScopeBridge,
)
from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_m77_protected_resources import (
    InjectedSealedInMemorySenderResource,
    ProtectedBindingClass,
)
from .bitrix_history_r0_reply_rollback_adapter import (
    InjectedPostDeleteHistoryReader,
    InjectedReplyDeleter,
)
from .bitrix_history_r0_roundtrip_rollback_composition import (
    InjectedPostSendHistoryReader,
)
from .nia_client import NiaClientResult
from .output_review import BitrixMessagePayloadPreview
from .preflight import NiaTextPayloadPreview


CloseCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class InjectedFixtureSenderResource:
    """Recurso inyectado explícitamente fixture, sin cliente o llamada real."""

    sender: object
    close_callback: CloseCallback
    fixture_only: bool = True
    real_client_constructed: bool = False
    external_calls: int = 0

    def __post_init__(self) -> None:
        if (
            self.sender is None
            or not callable(self.close_callback)
            or self.fixture_only is not True
            or self.real_client_constructed is not False
            or self.external_calls != 0
        ):
            raise ValueError("m70_fixture_sender_resource_invalid")

    async def close(self) -> None:
        await self.close_callback()


ProtectedSenderResource = (
    InjectedFixtureSenderResource | InjectedSealedInMemorySenderResource
)
FixtureSenderFactory = Callable[[], Awaitable[ProtectedSenderResource]]


class _OneShotNiaSender:
    def __init__(self, factory: FixtureSenderFactory) -> None:
        if not callable(factory):
            raise TypeError("m70_nia_factory_invalid")
        self._factory: Optional[FixtureSenderFactory] = factory
        self._used = False
        self.factory_calls = 0
        self.sender_calls = 0
        self.close_calls = 0
        self.binding_class = ProtectedBindingClass.FIXTURE_DOUBLE

    async def send_approved_text(
        self, payload: NiaTextPayloadPreview
    ) -> NiaClientResult:
        if self._used or self._factory is None:
            self._factory = None
            return NiaClientResult.failed("m70_nia_sender_reuse_rejected")
        self._used = True
        factory, self._factory = self._factory, None
        resource: Optional[ProtectedSenderResource] = None
        result: object = None
        close_failed = False
        try:
            self.factory_calls = 1
            raw = await factory()
            if type(raw) not in (
                InjectedFixtureSenderResource,
                InjectedSealedInMemorySenderResource,
            ):
                return NiaClientResult.failed("m70_nia_factory_result_invalid")
            resource = raw
            if type(raw) is InjectedSealedInMemorySenderResource:
                self.binding_class = ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            method = getattr(resource.sender, "send_approved_text", None)
            if not callable(method):
                return NiaClientResult.failed("m70_nia_sender_invalid")
            self.sender_calls = 1
            try:
                result = await method(payload)
            except Exception:
                return NiaClientResult.failed("m70_nia_sender_failed_safe")
        except Exception:
            return NiaClientResult.failed("m70_nia_factory_failed_safe")
        finally:
            if resource is not None:
                self.close_calls = 1
                try:
                    await resource.close()
                except Exception:
                    close_failed = True
            resource = None
            factory = None
        if close_failed:
            return NiaClientResult.failed("m70_nia_close_failed_safe")
        if not isinstance(result, NiaClientResult):
            return NiaClientResult.failed("m70_nia_result_invalid")
        return result

    @property
    def cleared(self) -> bool:
        return self._factory is None


class _OneShotBitrixSender:
    def __init__(self, factory: FixtureSenderFactory) -> None:
        if not callable(factory):
            raise TypeError("m70_bitrix_factory_invalid")
        self._factory: Optional[FixtureSenderFactory] = factory
        self._used = False
        self.factory_calls = 0
        self.sender_calls = 0
        self.close_calls = 0
        self.binding_class = ProtectedBindingClass.FIXTURE_DOUBLE

    async def send_approved_message(
        self, payload: BitrixMessagePayloadPreview
    ) -> BitrixClientResult:
        if self._used or self._factory is None:
            self._factory = None
            return BitrixClientResult.failed("m70_bitrix_sender_reuse_rejected")
        self._used = True
        factory, self._factory = self._factory, None
        resource: Optional[ProtectedSenderResource] = None
        result: object = None
        close_failed = False
        try:
            self.factory_calls = 1
            raw = await factory()
            if type(raw) not in (
                InjectedFixtureSenderResource,
                InjectedSealedInMemorySenderResource,
            ):
                return BitrixClientResult.failed("m70_bitrix_factory_result_invalid")
            resource = raw
            if type(raw) is InjectedSealedInMemorySenderResource:
                self.binding_class = ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            method = getattr(resource.sender, "send_approved_message", None)
            if not callable(method):
                return BitrixClientResult.failed("m70_bitrix_sender_invalid")
            self.sender_calls = 1
            try:
                result = await method(payload)
            except Exception:
                return BitrixClientResult.failed("m70_bitrix_sender_failed_safe")
        except Exception:
            return BitrixClientResult.failed("m70_bitrix_factory_failed_safe")
        finally:
            if resource is not None:
                self.close_calls = 1
                try:
                    await resource.close()
                except Exception:
                    close_failed = True
            resource = None
            factory = None
        if close_failed:
            return BitrixClientResult.failed("m70_bitrix_close_failed_safe")
        if not isinstance(result, BitrixClientResult):
            return BitrixClientResult.failed("m70_bitrix_result_invalid")
        return result

    @property
    def cleared(self) -> bool:
        return self._factory is None


class SenderFactoryCompositionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ROLLED_BACK = "ROLLED-BACK"
    NO_GO = "NO-GO"


class SenderFactoryCompositionResult(BaseModel):
    """Resumen M70 allowlisted; no conserva payloads, respuestas o recursos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M70"] = "M70"
    status: SenderFactoryCompositionStatus
    reason: Literal[
        "m70_senders_verified_with_m69",
        "m70_m69_rollback_verified",
        "m70_m69_no_go",
        "m70_reuse_rejected",
    ]
    m69_call_count: int = Field(ge=0, le=1)
    nia_factory_calls: int = Field(ge=0, le=1)
    nia_sender_calls: int = Field(ge=0, le=1)
    nia_close_calls: int = Field(ge=0, le=1)
    bitrix_factory_calls: int = Field(ge=0, le=1)
    bitrix_sender_calls: int = Field(ge=0, le=1)
    bitrix_close_calls: int = Field(ge=0, le=1)
    private_state_cleared: Literal[True] = True
    no_retry: Literal[True] = True
    binding_class: Literal[
        "fixture-double", "sealed-in-memory-concrete"
    ] = "fixture-double"
    fixture_only: bool = True
    concrete_clients_constructed_in_memory: bool = False
    network_capable_resources_accepted: Literal[False] = False
    real_clients_constructed: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    authorization_present: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class SenderFactoryM69Composition:
    """Vincula dos fábricas fixture one-shot al recorrido M69."""

    def __init__(
        self,
        *,
        plan: ProtectedRealRoundtripPlan,
        preflight_adapter: CombinedR1PreflightAdapter,
        history_reader: InjectedPostAnchorHistoryReader,
        nia_sender_factory: FixtureSenderFactory,
        bitrix_sender_factory: FixtureSenderFactory,
        post_send_history_reader: InjectedPostSendHistoryReader,
        deleter: InjectedReplyDeleter,
        post_delete_history_reader: InjectedPostDeleteHistoryReader,
        expected_sender_id: Optional[int] = None,
        emergency_rollback: bool = False,
    ) -> None:
        dependencies = (
            preflight_adapter,
            history_reader,
            nia_sender_factory,
            bitrix_sender_factory,
            post_send_history_reader,
            deleter,
            post_delete_history_reader,
        )
        if (
            not isinstance(plan, ProtectedRealRoundtripPlan)
            or not isinstance(preflight_adapter, CombinedR1PreflightAdapter)
            or any(item is None for item in dependencies)
            or not callable(nia_sender_factory)
            or not callable(bitrix_sender_factory)
        ):
            raise ValueError("m70_composition_contract_invalid")
        self._dependencies: Optional[tuple[object, ...]] = (
            plan,
            *dependencies,
            expected_sender_id,
            emergency_rollback,
        )
        self._used = False

    def clear(self) -> None:
        self._dependencies = None

    @property
    def cleared(self) -> bool:
        return self._dependencies is None

    @staticmethod
    def _result(
        reason: str,
        *,
        m69_calls: int,
        nia: Optional[_OneShotNiaSender] = None,
        bitrix: Optional[_OneShotBitrixSender] = None,
        verified: bool = False,
        rolled_back: bool = False,
    ) -> SenderFactoryCompositionResult:
        binding_class = (
            bitrix.binding_class
            if bitrix is not None
            else (
                nia.binding_class
                if nia is not None
                else ProtectedBindingClass.FIXTURE_DOUBLE
            )
        )
        if (
            nia is not None
            and bitrix is not None
            and nia.binding_class is not bitrix.binding_class
        ):
            reason = "m70_m69_no_go"
            verified = False
            rolled_back = False
        return SenderFactoryCompositionResult(
            status=(
                SenderFactoryCompositionStatus.ROLLED_BACK
                if rolled_back
                else (
                    SenderFactoryCompositionStatus.VERIFIED
                    if verified
                    else SenderFactoryCompositionStatus.NO_GO
                )
            ),
            reason=reason,
            m69_call_count=m69_calls,
            nia_factory_calls=nia.factory_calls if nia else 0,
            nia_sender_calls=nia.sender_calls if nia else 0,
            nia_close_calls=nia.close_calls if nia else 0,
            bitrix_factory_calls=bitrix.factory_calls if bitrix else 0,
            bitrix_sender_calls=bitrix.sender_calls if bitrix else 0,
            bitrix_close_calls=bitrix.close_calls if bitrix else 0,
            binding_class=binding_class.value,
            fixture_only=binding_class is ProtectedBindingClass.FIXTURE_DOUBLE,
            concrete_clients_constructed_in_memory=(
                binding_class
                is ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            ),
        )

    async def run_once(self) -> SenderFactoryCompositionResult:
        if self._used or self._dependencies is None:
            self.clear()
            return self._result("m70_reuse_rejected", m69_calls=0)
        self._used = True
        dependencies, self._dependencies = self._dependencies, None
        nia: Optional[_OneShotNiaSender] = None
        bitrix: Optional[_OneShotBitrixSender] = None
        try:
            (
                plan,
                preflight_adapter,
                history_reader,
                nia_factory,
                bitrix_factory,
                post_send_history_reader,
                deleter,
                post_delete_history_reader,
                expected_sender_id,
                emergency_rollback,
            ) = dependencies
            nia = _OneShotNiaSender(nia_factory)
            bitrix = _OneShotBitrixSender(bitrix_factory)
            bridge = PostAnchorExactScopeBridge(
                plan=plan,
                preflight_adapter=preflight_adapter,
                history_reader=history_reader,
                nia_sender=nia,
                bitrix_sender=bitrix,
                post_send_history_reader=post_send_history_reader,
                deleter=deleter,
                post_delete_history_reader=post_delete_history_reader,
                expected_sender_id=expected_sender_id,
                emergency_rollback=emergency_rollback,
            )
            result = await bridge.run_once()
            verified = result.status is PostAnchorBridgeStatus.VERIFIED
            rolled_back = result.status is PostAnchorBridgeStatus.ROLLED_BACK
            return self._result(
                (
                    "m70_senders_verified_with_m69"
                    if verified
                    else (
                        "m70_m69_rollback_verified"
                        if rolled_back
                        else "m70_m69_no_go"
                    )
                ),
                m69_calls=1,
                nia=nia,
                bitrix=bitrix,
                verified=verified,
                rolled_back=rolled_back,
            )
        finally:
            dependencies = ()
            self.clear()


__all__ = [
    "FixtureSenderFactory",
    "InjectedFixtureSenderResource",
    "SenderFactoryCompositionResult",
    "SenderFactoryCompositionStatus",
    "SenderFactoryM69Composition",
]
