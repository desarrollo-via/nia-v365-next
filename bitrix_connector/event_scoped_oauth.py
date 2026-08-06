"""OAuth efímero entregado por un evento webhook ``imbot.v2``.

El token del bot sólo existe durante el manejo del evento, no se persiste y no
expone capacidad de renovación.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Mapping, Optional

from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)


BOT_EVENT_ACCESS_TOKEN_KEY = "data[bot][auth][access_token]"
MAX_EVENT_SCOPED_OAUTH_BYTES = 8 * 1024


def _zeroize(value: bytearray) -> None:
    value[:] = b"\x00" * len(value)


@dataclass(frozen=True)
class EventScopedOAuthSnapshot:
    phase: Literal["M86-CD"] = "M86-CD"
    state: Literal["READY", "NO-GO", "CANCELLED"] = "NO-GO"
    reason: str = "event_scoped_oauth_not_run"
    token_transfer_calls: int = 0
    operation_calls: int = 0
    token_view_reads: int = 0
    refresh_calls: Literal[0] = 0
    persistence_calls: Literal[0] = 0
    resources_closed: bool = True
    token_buffer_zeroized: bool = True
    retry_budget: Literal[0] = 0
    external_calls: Literal[0] = 0


EventScopedOAuthOperation = Callable[[StoredOAuthAccessView], Awaitable[None]]


class EventScopedOAuthOwner:
    """Transfiere una vez el token privado del bot y destruye su buffer."""

    __slots__ = ("_token", "_used")

    def __init__(self, *, token: bytearray) -> None:
        if (
            type(token) is not bytearray
            or not token
            or len(token) > MAX_EVENT_SCOPED_OAUTH_BYTES
            or b"\x00" in token
        ):
            if type(token) is bytearray:
                _zeroize(token)
            raise ValueError("event_scoped_oauth_token_invalid")
        self._token: Optional[bytearray] = token
        self._used = False

    @classmethod
    def take_from_form_once(
        cls,
        form: dict[str, object],
    ) -> "EventScopedOAuthOwner":
        if type(form) is not dict:
            raise TypeError("event_scoped_oauth_form_invalid")
        raw = form.pop(BOT_EVENT_ACCESS_TOKEN_KEY, None)
        if raw is None or hasattr(raw, "filename"):
            raise ValueError("event_scoped_oauth_missing")
        text = str(raw).strip()
        if not text or "\x00" in text:
            raise ValueError("event_scoped_oauth_token_invalid")
        token = bytearray(text, "utf-8")
        text = ""
        return cls(token=token)

    async def run_once(
        self,
        operation: EventScopedOAuthOperation,
    ) -> EventScopedOAuthSnapshot:
        if self._used or self._token is None or not callable(operation):
            return EventScopedOAuthSnapshot(
                reason="event_scoped_oauth_reuse_or_operation_invalid",
            )
        self._used = True
        token, self._token = self._token, None
        view: Optional[StoredOAuthAccessView] = None
        state = "NO-GO"
        reason = "event_scoped_oauth_operation_failed_safe"
        operation_calls = 0
        try:
            view = StoredOAuthAccessView(token)
            operation_calls = 1
            result = await operation(view)
            if result is not None:
                raise TypeError("event_scoped_oauth_operation_result_invalid")
            state = "READY"
            reason = "event_scoped_oauth_used_without_refresh_or_persistence"
        except asyncio.CancelledError:
            state = "CANCELLED"
            reason = "event_scoped_oauth_cancelled"
        except Exception:
            state = "NO-GO"
        finally:
            reads = view.reads if view is not None else 0
            if view is not None:
                view.close()
            _zeroize(token)
        return EventScopedOAuthSnapshot(
            state=state,
            reason=reason,
            token_transfer_calls=1,
            operation_calls=operation_calls,
            token_view_reads=reads,
        )

    def close(self) -> None:
        token, self._token = self._token, None
        if type(token) is bytearray:
            _zeroize(token)
        self._used = True

    def __repr__(self) -> str:
        return "EventScopedOAuthOwner(<redacted>)"


def event_scoped_oauth_is_documented_for_webhook_mode(
    event_shape: Mapping[str, object],
) -> bool:
    """Auditoría pura: sólo reconoce la clave oficial anidada y no la lee."""

    return (
        isinstance(event_shape, Mapping)
        and BOT_EVENT_ACCESS_TOKEN_KEY in event_shape
        and "auth[application_token]" in event_shape
    )


__all__ = [
    "BOT_EVENT_ACCESS_TOKEN_KEY",
    "EventScopedOAuthOwner",
    "EventScopedOAuthSnapshot",
    "MAX_EVENT_SCOPED_OAUTH_BYTES",
    "event_scoped_oauth_is_documented_for_webhook_mode",
]
