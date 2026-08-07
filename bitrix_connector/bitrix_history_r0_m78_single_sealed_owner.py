"""Owner M78 que integra M73 y la cadena sellada M75/M76/M70/M71."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_m73_single_fixture_owner import SingleFixtureR1Owner
from .bitrix_history_r0_m75_dormant_real_bindings import (
    DormantBindingStatus,
    DormantRealBindingOwner,
)
from .bitrix_history_r0_m76_in_memory_concrete_builders import (
    ConcreteBindingStatus,
    InMemoryConcreteBindingBuilders,
)


class SingleSealedOwnerStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NO_GO = "NO-GO"
    CANCELLED = "CANCELLED"


class SingleSealedOwnerSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M78"] = "M78"
    status: SingleSealedOwnerStatus
    reason: Literal[
        "m78_m73_m77_sealed_rollback_verified",
        "m78_single_sealed_owner_no_go",
        "m78_single_sealed_owner_cancelled",
        "m78_reuse_rejected",
    ]
    m73_calls: int = Field(ge=0, le=1)
    literal_read_calls: int = Field(ge=0, le=3)
    preflight_probe_calls: int = Field(ge=0, le=1)
    attention_probe_calls: int = Field(ge=0, le=1)
    exact_scope_owner_calls: int = Field(ge=0, le=1)
    oauth_loader_calls: int = Field(ge=0, le=1)
    oauth_refresh_calls: Literal[0] = 0
    concrete_builder_calls: int = Field(ge=0, le=4)
    dependency_close_calls: int = Field(ge=0, le=4)
    http_close_calls: int = Field(ge=0, le=4)
    binding_class: Literal["sealed-in-memory-concrete"] = (
        "sealed-in-memory-concrete"
    )
    fixture_attention_boundary_verified: bool = False
    sealed_exact_scope_verified: bool = False
    sealed_rollback_verified: bool = False
    fixture_masquerade_used: Literal[False] = False
    transport_in_memory_only: Literal[True] = True
    network_capable_resources_accepted: Literal[False] = False
    all_private_owners_closed: bool = False
    call_budget_per_binding: Literal[1] = 1
    retry_budget: Literal[0] = 0
    maximum_http_timeout_seconds: Literal[10] = 10
    real_authorizations_consumed: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    point_8_can_begin: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    human_message_requested: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class SingleSealedM73M77Owner:
    def __init__(
        self,
        *,
        m73_owner: SingleFixtureR1Owner,
        binding_owner: DormantRealBindingOwner,
        concrete_builders: InMemoryConcreteBindingBuilders,
    ) -> None:
        if (
            not isinstance(m73_owner, SingleFixtureR1Owner)
            or not isinstance(binding_owner, DormantRealBindingOwner)
            or not isinstance(concrete_builders, InMemoryConcreteBindingBuilders)
        ):
            raise ValueError("m78_single_sealed_owner_invalid")
        self._m73_owner: Optional[SingleFixtureR1Owner] = m73_owner
        self._binding_owner: Optional[DormantRealBindingOwner] = binding_owner
        self._concrete_builders: Optional[InMemoryConcreteBindingBuilders] = (
            concrete_builders
        )
        self._used = False

    def __repr__(self) -> str:
        return "SingleSealedM73M77Owner(<redacted>)"

    async def run_once(self) -> SingleSealedOwnerSnapshot:
        if (
            self._used
            or self._m73_owner is None
            or self._binding_owner is None
            or self._concrete_builders is None
        ):
            self._used = True
            return SingleSealedOwnerSnapshot(
                status=SingleSealedOwnerStatus.NO_GO,
                reason="m78_reuse_rejected",
                m73_calls=0,
                literal_read_calls=0,
                preflight_probe_calls=0,
                attention_probe_calls=0,
                exact_scope_owner_calls=0,
                oauth_loader_calls=0,
                concrete_builder_calls=0,
                dependency_close_calls=0,
                http_close_calls=0,
            )
        self._used = True
        m73_owner, self._m73_owner = self._m73_owner, None
        binding_owner, self._binding_owner = self._binding_owner, None
        concrete_builders, self._concrete_builders = self._concrete_builders, None
        m73 = None
        binding = None
        concrete = None
        try:
            m73 = await m73_owner.run_once()
        except Exception:
            m73 = None
        finally:
            try:
                binding = await binding_owner.close()
            except BaseException:
                binding = None
            try:
                concrete = await concrete_builders.close()
            except BaseException:
                concrete = None
            m73_owner = None
            binding_owner = None
            concrete_builders = None
        verified = (
            m73 is not None
            and m73.state == "PREPARED"
            and m73.binding_class == "sealed-in-memory-concrete"
            and m73.exact_scope_verified_in_sealed_memory
            and m73.exact_scope_rollback_verified
            and binding is not None
            and binding.status is DormantBindingStatus.VERIFIED
            and binding.binding_class == "sealed-in-memory-concrete"
            and concrete is not None
            and concrete.status is ConcreteBindingStatus.VERIFIED
        )
        cancelled = m73 is not None and m73.state == "CANCELLED"
        return SingleSealedOwnerSnapshot(
            status=(
                SingleSealedOwnerStatus.VERIFIED
                if verified
                else (
                    SingleSealedOwnerStatus.CANCELLED
                    if cancelled
                    else SingleSealedOwnerStatus.NO_GO
                )
            ),
            reason=(
                "m78_m73_m77_sealed_rollback_verified"
                if verified
                else (
                    "m78_single_sealed_owner_cancelled"
                    if cancelled
                    else "m78_single_sealed_owner_no_go"
                )
            ),
            m73_calls=1,
            literal_read_calls=m73.literal_read_calls if m73 else 0,
            preflight_probe_calls=m73.preflight_probe_calls if m73 else 0,
            attention_probe_calls=m73.attention_probe_calls if m73 else 0,
            exact_scope_owner_calls=m73.exact_scope_owner_calls if m73 else 0,
            oauth_loader_calls=binding.oauth_loader_calls if binding else 0,
            concrete_builder_calls=(
                concrete.http_resource_factory_calls if concrete else 0
            ),
            dependency_close_calls=(
                binding.dependency_close_calls if binding else 0
            ),
            http_close_calls=concrete.close_calls if concrete else 0,
            fixture_attention_boundary_verified=(
                m73.fixture_attention_boundary_verified if m73 else False
            ),
            sealed_exact_scope_verified=(
                m73.exact_scope_verified_in_sealed_memory if m73 else False
            ),
            sealed_rollback_verified=(
                m73.exact_scope_rollback_verified if m73 else False
            ),
            all_private_owners_closed=(binding is not None and concrete is not None),
        )


__all__ = [
    "SingleSealedM73M77Owner",
    "SingleSealedOwnerSnapshot",
    "SingleSealedOwnerStatus",
]
