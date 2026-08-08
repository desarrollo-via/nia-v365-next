"""Composición M71 hermética de rollback y verificación creados por fábricas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_m68_combined_preflight import CombinedR1PreflightAdapter
from .bitrix_history_r0_m69_post_anchor_bridge import InjectedPostAnchorHistoryReader
from .bitrix_history_r0_m70_sender_factory_composition import (
    FixtureSenderFactory,
    SenderFactoryCompositionStatus,
    SenderFactoryM69Composition,
)
from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_m77_protected_resources import (
    InjectedSealedInMemoryRollbackResource,
    ProtectedBindingClass,
)
from .bitrix_history_r0_reply_rollback_contract import ReplyRollbackDeletePreview
from .bitrix_history_r0_roundtrip_rollback_composition import (
    InjectedPostSendHistoryReader,
)


CloseCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class InjectedFixtureRollbackResource:
    """Recurso de rollback fixture; no contiene fuente ni cliente real."""

    dependency: object
    close_callback: CloseCallback
    fixture_only: bool = True
    real_client_constructed: bool = False
    external_calls: int = 0

    def __post_init__(self) -> None:
        if (
            self.dependency is None
            or not callable(self.close_callback)
            or self.fixture_only is not True
            or self.real_client_constructed is not False
            or self.external_calls != 0
        ):
            raise ValueError("m71_fixture_rollback_resource_invalid")

    async def close(self) -> None:
        await self.close_callback()


ProtectedRollbackResource = (
    InjectedFixtureRollbackResource | InjectedSealedInMemoryRollbackResource
)
FixtureRollbackFactory = Callable[[], Awaitable[ProtectedRollbackResource]]


class _OneShotReplyDeleter:
    def __init__(self, factory: FixtureRollbackFactory) -> None:
        if not callable(factory):
            raise TypeError("m71_deleter_factory_invalid")
        self._factory: Optional[FixtureRollbackFactory] = factory
        self._used = False
        self.factory_calls = 0
        self.delete_calls = 0
        self.close_calls = 0
        self.binding_class = ProtectedBindingClass.FIXTURE_DOUBLE

    async def delete_approved_reply(
        self, preview: ReplyRollbackDeletePreview
    ) -> object:
        if self._used or self._factory is None:
            self._factory = None
            return {"result": {"result": False}}
        self._used = True
        factory, self._factory = self._factory, None
        resource: Optional[ProtectedRollbackResource] = None
        response: object = {"result": {"result": False}}
        close_failed = False
        try:
            self.factory_calls = 1
            raw = await factory()
            if type(raw) not in (
                InjectedFixtureRollbackResource,
                InjectedSealedInMemoryRollbackResource,
            ):
                return response
            resource = raw
            if type(raw) is InjectedSealedInMemoryRollbackResource:
                self.binding_class = ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            method = getattr(resource.dependency, "delete_approved_reply", None)
            if not callable(method):
                return response
            self.delete_calls = 1
            try:
                response = await method(preview)
            except Exception:
                return {"result": {"result": False}}
        except Exception:
            return response
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
            return {"result": {"result": False}}
        return response

    @property
    def cleared(self) -> bool:
        return self._factory is None


class _OneShotPostDeleteReader:
    def __init__(self, factory: FixtureRollbackFactory) -> None:
        if not callable(factory):
            raise TypeError("m71_reader_factory_invalid")
        self._factory: Optional[FixtureRollbackFactory] = factory
        self._used = False
        self.factory_calls = 0
        self.read_calls = 0
        self.close_calls = 0
        self.binding_class = ProtectedBindingClass.FIXTURE_DOUBLE

    async def read_post_delete_history(self, *, session_id: int) -> object:
        if self._used or self._factory is None:
            self._factory = None
            raise RuntimeError("m71_post_delete_reader_reuse_rejected")
        self._used = True
        factory, self._factory = self._factory, None
        resource: Optional[ProtectedRollbackResource] = None
        response: object = None
        close_failed = False
        try:
            self.factory_calls = 1
            raw = await factory()
            if type(raw) not in (
                InjectedFixtureRollbackResource,
                InjectedSealedInMemoryRollbackResource,
            ):
                raise RuntimeError("m71_reader_factory_result_invalid")
            resource = raw
            if type(raw) is InjectedSealedInMemoryRollbackResource:
                self.binding_class = ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            method = getattr(
                resource.dependency, "read_post_delete_history", None
            )
            if not callable(method):
                raise RuntimeError("m71_post_delete_reader_invalid")
            self.read_calls = 1
            response = await method(session_id=session_id)
        except Exception as exc:
            raise RuntimeError("m71_post_delete_read_failed_safe") from None
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
            raise RuntimeError("m71_post_delete_close_failed_safe")
        return response

    @property
    def cleared(self) -> bool:
        return self._factory is None


class RollbackFactoryCompositionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ROLLED_BACK = "ROLLED-BACK"
    NO_GO = "NO-GO"


class RollbackFactoryCompositionResult(BaseModel):
    """Resumen M71 redactado sin ID, payload, respuesta o recurso."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M71"] = "M71"
    status: RollbackFactoryCompositionStatus
    reason: Literal[
        "m71_rollback_verified_with_m70",
        "m71_rollback_not_exercised",
        "m71_rollback_no_go",
        "m71_reuse_rejected",
    ]
    m70_call_count: int = Field(ge=0, le=1)
    deleter_factory_calls: int = Field(ge=0, le=1)
    delete_calls: int = Field(ge=0, le=1)
    deleter_close_calls: int = Field(ge=0, le=1)
    reader_factory_calls: int = Field(ge=0, le=1)
    post_delete_read_calls: int = Field(ge=0, le=1)
    reader_close_calls: int = Field(ge=0, le=1)
    exact_receipt_path_required: Literal[True] = True
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
    real_rollback_executed: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class RollbackFactoryM70Composition:
    """Vincula fábricas fixture de borrado y relectura al recorrido M70."""

    def __init__(
        self,
        *,
        plan: ProtectedRealRoundtripPlan,
        preflight_adapter: CombinedR1PreflightAdapter,
        history_reader: InjectedPostAnchorHistoryReader,
        nia_sender_factory: FixtureSenderFactory,
        bitrix_sender_factory: FixtureSenderFactory,
        post_send_history_reader: InjectedPostSendHistoryReader,
        deleter_factory: FixtureRollbackFactory,
        post_delete_reader_factory: FixtureRollbackFactory,
        expected_sender_id: Optional[int] = None,
        emergency_rollback: bool = False,
    ) -> None:
        dependencies = (
            preflight_adapter,
            history_reader,
            nia_sender_factory,
            bitrix_sender_factory,
            post_send_history_reader,
            deleter_factory,
            post_delete_reader_factory,
        )
        if (
            not isinstance(plan, ProtectedRealRoundtripPlan)
            or not isinstance(preflight_adapter, CombinedR1PreflightAdapter)
            or any(item is None for item in dependencies)
            or not callable(deleter_factory)
            or not callable(post_delete_reader_factory)
        ):
            raise ValueError("m71_composition_contract_invalid")
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
        m70_calls: int,
        deleter: Optional[_OneShotReplyDeleter] = None,
        reader: Optional[_OneShotPostDeleteReader] = None,
        sender_binding_class: ProtectedBindingClass = (
            ProtectedBindingClass.FIXTURE_DOUBLE
        ),
        verified: bool = False,
        rolled_back: bool = False,
    ) -> RollbackFactoryCompositionResult:
        binding_class = sender_binding_class
        if rolled_back and deleter is not None and reader is not None:
            if not (
                deleter.binding_class is reader.binding_class
                and deleter.binding_class is sender_binding_class
            ):
                reason = "m71_rollback_no_go"
                rolled_back = False
        return RollbackFactoryCompositionResult(
            status=(
                RollbackFactoryCompositionStatus.ROLLED_BACK
                if rolled_back
                else (
                    RollbackFactoryCompositionStatus.VERIFIED
                    if verified
                    else RollbackFactoryCompositionStatus.NO_GO
                )
            ),
            reason=reason,
            m70_call_count=m70_calls,
            deleter_factory_calls=deleter.factory_calls if deleter else 0,
            delete_calls=deleter.delete_calls if deleter else 0,
            deleter_close_calls=deleter.close_calls if deleter else 0,
            reader_factory_calls=reader.factory_calls if reader else 0,
            post_delete_read_calls=reader.read_calls if reader else 0,
            reader_close_calls=reader.close_calls if reader else 0,
            binding_class=binding_class.value,
            fixture_only=binding_class is ProtectedBindingClass.FIXTURE_DOUBLE,
            concrete_clients_constructed_in_memory=(
                binding_class
                is ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            ),
        )

    async def run_once(self) -> RollbackFactoryCompositionResult:
        if self._used or self._dependencies is None:
            self.clear()
            return self._result("m71_reuse_rejected", m70_calls=0)
        self._used = True
        dependencies, self._dependencies = self._dependencies, None
        deleter: Optional[_OneShotReplyDeleter] = None
        reader: Optional[_OneShotPostDeleteReader] = None
        try:
            (
                plan,
                preflight_adapter,
                history_reader,
                nia_sender_factory,
                bitrix_sender_factory,
                post_send_history_reader,
                deleter_factory,
                post_delete_reader_factory,
                expected_sender_id,
                emergency_rollback,
            ) = dependencies
            deleter = _OneShotReplyDeleter(deleter_factory)
            reader = _OneShotPostDeleteReader(post_delete_reader_factory)
            composition = SenderFactoryM69Composition(
                plan=plan,
                preflight_adapter=preflight_adapter,
                history_reader=history_reader,
                nia_sender_factory=nia_sender_factory,
                bitrix_sender_factory=bitrix_sender_factory,
                post_send_history_reader=post_send_history_reader,
                deleter=deleter,
                post_delete_history_reader=reader,
                expected_sender_id=expected_sender_id,
                emergency_rollback=emergency_rollback,
            )
            result = await composition.run_once()
            rolled_back = (
                result.status is SenderFactoryCompositionStatus.ROLLED_BACK
            )
            verified = result.status is SenderFactoryCompositionStatus.VERIFIED
            if rolled_back:
                reason = "m71_rollback_verified_with_m70"
            elif verified:
                reason = "m71_rollback_not_exercised"
            else:
                reason = "m71_rollback_no_go"
            return self._result(
                reason,
                m70_calls=1,
                deleter=deleter,
                reader=reader,
                sender_binding_class=ProtectedBindingClass(result.binding_class),
                verified=verified,
                rolled_back=rolled_back,
            )
        finally:
            dependencies = ()
            self.clear()


__all__ = [
    "FixtureRollbackFactory",
    "InjectedFixtureRollbackResource",
    "RollbackFactoryCompositionResult",
    "RollbackFactoryCompositionStatus",
    "RollbackFactoryM70Composition",
]
