"""Owner M77 para componer M75/M76/M70/M71 sólo en memoria sellada."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_m71_rollback_factory_composition import (
    RollbackFactoryCompositionStatus,
    RollbackFactoryM70Composition,
)
from .bitrix_history_r0_m75_dormant_real_bindings import (
    DormantBindingStatus,
    DormantRealBindingOwner,
)
from .bitrix_history_r0_m76_in_memory_concrete_builders import (
    ConcreteBindingStatus,
    InMemoryConcreteBindingBuilders,
)
from .bitrix_history_r0_m77_protected_resources import ProtectedBindingClass


class SealedCompositionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"


class SealedCompositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M77"] = "M77"
    status: SealedCompositionStatus
    reason: Literal[
        "m77_m75_m76_m70_m71_sealed_in_memory_verified",
        "m77_sealed_composition_no_go",
        "m77_reuse_rejected",
    ]
    m71_calls: int = Field(ge=0, le=1)
    m75_close_calls: int = Field(ge=0, le=1)
    m76_close_calls: int = Field(ge=0, le=1)
    oauth_loader_calls: int = Field(ge=0, le=1)
    oauth_refresh_calls: Literal[0] = 0
    concrete_builder_calls: int = Field(ge=0, le=4)
    dependency_close_calls: int = Field(ge=0, le=4)
    http_close_calls: int = Field(ge=0, le=4)
    binding_class: Literal["sealed-in-memory-concrete"] = (
        "sealed-in-memory-concrete"
    )
    fixture_masquerade_used: Literal[False] = False
    transport_in_memory_only: Literal[True] = True
    network_capable_resources_accepted: Literal[False] = False
    call_budget_per_binding: Literal[1] = 1
    retry_budget: Literal[0] = 0
    maximum_timeout_seconds: Literal[10] = 10
    all_private_owners_closed: bool = False
    m73_connected: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class SealedInMemoryM75M76Owner:
    def __init__(
        self,
        *,
        composition: RollbackFactoryM70Composition,
        binding_owner: DormantRealBindingOwner,
        concrete_builders: InMemoryConcreteBindingBuilders,
    ) -> None:
        if (
            not isinstance(composition, RollbackFactoryM70Composition)
            or not isinstance(binding_owner, DormantRealBindingOwner)
            or not isinstance(concrete_builders, InMemoryConcreteBindingBuilders)
        ):
            raise ValueError("m77_sealed_owner_invalid")
        self._composition: Optional[RollbackFactoryM70Composition] = composition
        self._binding_owner: Optional[DormantRealBindingOwner] = binding_owner
        self._concrete_builders: Optional[InMemoryConcreteBindingBuilders] = (
            concrete_builders
        )
        self._used = False

    def __repr__(self) -> str:
        return "SealedInMemoryM75M76Owner(<redacted>)"

    async def run_once(self) -> SealedCompositionSnapshot:
        if (
            self._used
            or self._composition is None
            or self._binding_owner is None
            or self._concrete_builders is None
        ):
            self._used = True
            return SealedCompositionSnapshot(
                status=SealedCompositionStatus.NO_GO,
                reason="m77_reuse_rejected",
                m71_calls=0,
                m75_close_calls=0,
                m76_close_calls=0,
                oauth_loader_calls=0,
                concrete_builder_calls=0,
                dependency_close_calls=0,
                http_close_calls=0,
            )
        self._used = True
        composition, self._composition = self._composition, None
        binding_owner, self._binding_owner = self._binding_owner, None
        concrete_builders, self._concrete_builders = self._concrete_builders, None
        m71_result = None
        binding_snapshot = None
        concrete_snapshot = None
        cancelled: Optional[asyncio.CancelledError] = None
        try:
            m71_result = await composition.run_once()
        except asyncio.CancelledError as exc:
            cancelled = exc
        except Exception:
            pass
        finally:
            try:
                binding_snapshot = await binding_owner.close()
            except BaseException:
                binding_snapshot = None
            try:
                concrete_snapshot = await concrete_builders.close()
            except BaseException:
                concrete_snapshot = None
            composition = None
            binding_owner = None
            concrete_builders = None
        if cancelled is not None:
            raise cancelled
        verified = (
            m71_result is not None
            and m71_result.status is RollbackFactoryCompositionStatus.ROLLED_BACK
            and m71_result.binding_class
            == ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE.value
            and m71_result.network_capable_resources_accepted is False
            and binding_snapshot is not None
            and binding_snapshot.status is DormantBindingStatus.VERIFIED
            and binding_snapshot.binding_class
            == ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE.value
            and concrete_snapshot is not None
            and concrete_snapshot.status is ConcreteBindingStatus.VERIFIED
        )
        return SealedCompositionSnapshot(
            status=(
                SealedCompositionStatus.VERIFIED
                if verified
                else SealedCompositionStatus.NO_GO
            ),
            reason=(
                "m77_m75_m76_m70_m71_sealed_in_memory_verified"
                if verified
                else "m77_sealed_composition_no_go"
            ),
            m71_calls=1,
            m75_close_calls=1,
            m76_close_calls=1,
            oauth_loader_calls=(
                binding_snapshot.oauth_loader_calls if binding_snapshot else 0
            ),
            concrete_builder_calls=(
                concrete_snapshot.http_resource_factory_calls
                if concrete_snapshot
                else 0
            ),
            dependency_close_calls=(
                binding_snapshot.dependency_close_calls if binding_snapshot else 0
            ),
            http_close_calls=(
                concrete_snapshot.close_calls if concrete_snapshot else 0
            ),
            all_private_owners_closed=(
                binding_snapshot is not None and concrete_snapshot is not None
            ),
        )


__all__ = [
    "SealedCompositionSnapshot",
    "SealedCompositionStatus",
    "SealedInMemoryM75M76Owner",
]
