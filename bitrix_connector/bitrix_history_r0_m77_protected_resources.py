"""Envolturas M77 que distinguen fixture de cliente concreto sellado en memoria."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable


CloseCallback = Callable[[], Awaitable[None]]


class ProtectedBindingClass(str, Enum):
    FIXTURE_DOUBLE = "fixture-double"
    SEALED_IN_MEMORY_CONCRETE = "sealed-in-memory-concrete"


@dataclass(frozen=True)
class InjectedSealedInMemorySenderResource:
    sender: object
    close_callback: CloseCallback
    binding_class: ProtectedBindingClass = (
        ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
    )
    concrete_client_constructed: bool = True
    transport_in_memory_only: bool = True
    network_capable: bool = False
    external_calls: int = 0

    def __post_init__(self) -> None:
        if (
            self.sender is None
            or not callable(self.close_callback)
            or self.binding_class
            is not ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            or self.concrete_client_constructed is not True
            or self.transport_in_memory_only is not True
            or self.network_capable is not False
            or self.external_calls != 0
        ):
            raise ValueError("m77_sealed_sender_resource_invalid")

    async def close(self) -> None:
        await self.close_callback()


@dataclass(frozen=True)
class InjectedSealedInMemoryRollbackResource:
    dependency: object
    close_callback: CloseCallback
    binding_class: ProtectedBindingClass = (
        ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
    )
    concrete_client_constructed: bool = True
    transport_in_memory_only: bool = True
    network_capable: bool = False
    external_calls: int = 0

    def __post_init__(self) -> None:
        if (
            self.dependency is None
            or not callable(self.close_callback)
            or self.binding_class
            is not ProtectedBindingClass.SEALED_IN_MEMORY_CONCRETE
            or self.concrete_client_constructed is not True
            or self.transport_in_memory_only is not True
            or self.network_capable is not False
            or self.external_calls != 0
        ):
            raise ValueError("m77_sealed_rollback_resource_invalid")

    async def close(self) -> None:
        await self.close_callback()


__all__ = [
    "InjectedSealedInMemoryRollbackResource",
    "InjectedSealedInMemorySenderResource",
    "ProtectedBindingClass",
]
