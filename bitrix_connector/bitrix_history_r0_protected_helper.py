"""Núcleo hermético para consumir una allowlist protegida una sola vez."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol


PROTECTED_SETTING_NAMES = (
    "NIA_BITRIX_DOMAIN",
    "NIA_BITRIX_MEMBER_ID",
    "NIA_BITRIX_CLIENT_ID",
    "NIA_BITRIX_CLIENT_SECRET",
    "NIA_BITRIX_MONGO_URI",
    "NIA_BITRIX_MONGO_DB",
    "NIA_BITRIX_INSTALLATIONS_COLLECTION",
)

ProtectedFailureCategory = Literal[
    "none",
    "protected_source_api_unavailable",
    "protected_source_record_unavailable",
    "protected_source_blob_invalid",
    "protected_source_contract_invalid",
    "protected_source_open_failed",
    "protected_values_transfer_failed",
    "protected_operation_failed",
    "protected_settings_validation_failed",
    "oauth_load_failed",
    "lifecycle_operation_failed",
    "protected_resources_close_failed",
    "cancelled",
]
PROTECTED_FAILURE_CATEGORIES: tuple[ProtectedFailureCategory, ...] = (
    "none",
    "protected_source_api_unavailable",
    "protected_source_record_unavailable",
    "protected_source_blob_invalid",
    "protected_source_contract_invalid",
    "protected_source_open_failed",
    "protected_values_transfer_failed",
    "protected_operation_failed",
    "protected_settings_validation_failed",
    "oauth_load_failed",
    "lifecycle_operation_failed",
    "protected_resources_close_failed",
    "cancelled",
)

PROTECTED_SOURCE_OPEN_FAILURE_CATEGORIES = frozenset(
    {
        "protected_source_api_unavailable",
        "protected_source_record_unavailable",
        "protected_source_blob_invalid",
        "protected_source_contract_invalid",
    }
)


class ProtectedSourceOpenFailure(RuntimeError):
    """Transporta sólo una causa pública allowlisted, nunca el detalle privado."""

    __slots__ = ("category",)

    def __init__(self, category: ProtectedFailureCategory) -> None:
        if category not in PROTECTED_SOURCE_OPEN_FAILURE_CATEGORIES:
            raise ValueError("protected_source_open_failure_category_invalid")
        super().__init__("protected_source_open_failure")
        self.category = category


class ProtectedHelperState(str, Enum):
    READY = "READY"
    NO_GO = "NO-GO"
    CANCELLED = "CANCELLED"


class ProtectedValueSource(Protocol):
    """Transfiere buffers propios; el helper los invalida al terminar."""

    async def open(self) -> None: ...

    async def read(self, name: str) -> bytearray: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class ProtectedHelperSnapshot:
    """Salida pública cerrada sin nombres ni características de valores."""

    state: ProtectedHelperState = ProtectedHelperState.NO_GO
    reason: str = "protected_helper_not_started"
    protected_source_opened: bool = False
    required_values_present: bool = False
    operation_completed: bool = False
    resources_closed: bool = False
    source_read_calls: int = 0
    operation_calls: int = 0
    failure_category: ProtectedFailureCategory = "none"


class ProtectedValueView:
    """Vista efímera allowlisted que nunca representa sus buffers."""

    __slots__ = ("_active", "_buffers")

    def __init__(self, buffers: dict[str, bytearray]) -> None:
        self._buffers = buffers
        self._active = True

    def read_text(self, name: str) -> str:
        if not self._active:
            raise RuntimeError("protected_helper_view_closed")
        if name not in PROTECTED_SETTING_NAMES or name not in self._buffers:
            raise KeyError("protected_helper_name_not_allowed")
        return bytes(self._buffers[name]).decode("utf-8")

    def close(self) -> None:
        self._active = False

    def __repr__(self) -> str:
        return "ProtectedValueView(<redacted>)"


ProtectedOperation = Callable[[ProtectedValueView], Awaitable[None]]


def _zeroize(buffers: dict[str, bytearray]) -> None:
    for value in buffers.values():
        value[:] = b"\x00" * len(value)
    buffers.clear()


async def execute_protected_helper_once(
    *,
    source: ProtectedValueSource,
    operation: ProtectedOperation,
) -> ProtectedHelperSnapshot:
    """Consume la allowlist una vez, falla cerrado y limpia siempre."""

    buffers: dict[str, bytearray] = {}
    view: ProtectedValueView | None = None
    source_opened = False
    required_values_present = False
    operation_completed = False
    resources_closed = False
    source_read_calls = 0
    operation_calls = 0
    state = ProtectedHelperState.NO_GO
    reason = "protected_helper_failed_safe"
    failure_category: ProtectedFailureCategory = "none"
    stage = "source_open"

    try:
        await source.open()
        source_opened = True
        stage = "value_transfer"
        for name in PROTECTED_SETTING_NAMES:
            value = await source.read(name)
            source_read_calls += 1
            if type(value) is not bytearray or not value:
                raise ValueError("protected_helper_required_values_missing")
            buffers[name] = value

        required_values_present = True
        stage = "operation"
        view = ProtectedValueView(buffers)
        operation_calls = 1
        operation_result = await operation(view)
        if operation_result is not None:
            raise TypeError("protected_helper_operation_result_invalid")
        operation_completed = True
        state = ProtectedHelperState.READY
        reason = "protected_helper_completed"
    except asyncio.CancelledError:
        state = ProtectedHelperState.CANCELLED
        reason = "protected_helper_cancelled"
        failure_category = "cancelled"
    except ProtectedSourceOpenFailure as error:
        state = ProtectedHelperState.NO_GO
        reason = "protected_helper_failed_safe"
        failure_category = error.category
    except Exception:
        state = ProtectedHelperState.NO_GO
        reason = "protected_helper_failed_safe"
        failure_category = {
            "source_open": "protected_source_open_failed",
            "value_transfer": "protected_values_transfer_failed",
            "operation": "protected_operation_failed",
        }[stage]
    finally:
        if view is not None:
            view.close()
        _zeroize(buffers)
        try:
            await source.close()
        except Exception:
            state = ProtectedHelperState.NO_GO
            reason = "protected_helper_close_failed"
            failure_category = "protected_resources_close_failed"
        else:
            resources_closed = True

    return ProtectedHelperSnapshot(
        state=state,
        reason=reason,
        protected_source_opened=source_opened,
        required_values_present=required_values_present,
        operation_completed=operation_completed,
        resources_closed=resources_closed,
        source_read_calls=(
            len(PROTECTED_SETTING_NAMES) if required_values_present else 0
        ),
        operation_calls=operation_calls,
        failure_category=failure_category,
    )


__all__ = [
    "PROTECTED_SETTING_NAMES",
    "PROTECTED_FAILURE_CATEGORIES",
    "PROTECTED_SOURCE_OPEN_FAILURE_CATEGORIES",
    "ProtectedFailureCategory",
    "ProtectedHelperSnapshot",
    "ProtectedHelperState",
    "ProtectedOperation",
    "ProtectedSourceOpenFailure",
    "ProtectedValueSource",
    "ProtectedValueView",
    "execute_protected_helper_once",
]
