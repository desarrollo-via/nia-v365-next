"""Barreras ASGI acotadas para el ingreso público G0."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(frozen=True)
class G0IngressLimits:
    max_body_bytes: int = 262_144
    request_timeout_seconds: float = 5.0
    rate_limit_requests: int = 60
    rate_window_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_body_bytes <= 0:
            raise ValueError("g0_max_body_bytes_invalid")
        if self.request_timeout_seconds <= 0:
            raise ValueError("g0_request_timeout_invalid")
        if self.rate_limit_requests <= 0:
            raise ValueError("g0_rate_limit_invalid")
        if self.rate_window_seconds <= 0:
            raise ValueError("g0_rate_window_invalid")


class G0StopController:
    """Parada terminal local; no ofrece ruta HTTP para reactivarse."""

    def __init__(self) -> None:
        self._stopped = False
        self._event: Optional[asyncio.Event] = None

    @property
    def stopped(self) -> bool:
        return self._stopped

    def request_stop(self) -> None:
        self._stopped = True
        if self._event is not None:
            self._event.set()

    async def wait(self) -> None:
        if self._stopped:
            return
        if self._event is None:
            self._event = asyncio.Event()
        if self._stopped:
            self._event.set()
        await self._event.wait()


class G0IngressGuard:
    """Conserva solo las marcas necesarias para una ventana global."""

    def __init__(
        self,
        *,
        limits: G0IngressLimits,
        stop_controller: G0StopController,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits
        self.stop_controller = stop_controller
        self._clock = clock
        self._accepted_at: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def admit(self) -> bool:
        now = self._clock()
        cutoff = now - self.limits.rate_window_seconds
        async with self._lock:
            while self._accepted_at and self._accepted_at[0] <= cutoff:
                self._accepted_at.popleft()
            if len(self._accepted_at) >= self.limits.rate_limit_requests:
                return False
            self._accepted_at.append(now)
            return True

    @property
    def tracked_request_count(self) -> int:
        return len(self._accepted_at)


class _BodyTooLarge(Exception):
    pass


class _ClientDisconnected(Exception):
    pass


class _IngressStopped(Exception):
    pass


class G0IngressGuardMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        guard: G0IngressGuard,
        webhook_path: str,
    ) -> None:
        self.app = app
        self.guard = guard
        self.webhook_path = webhook_path

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get("path") != self.webhook_path
            or scope.get("method") != "POST"
        ):
            await self.app(scope, receive, send)
            return

        if self.guard.stop_controller.stopped:
            await self._reject(send, 503, "disabled", "g0_ingress_stopped")
            return

        try:
            content_length = self._content_length(scope)
        except ValueError:
            await self._reject(send, 400, "invalid", "g0_content_length_invalid")
            return
        if (
            content_length is not None
            and content_length > self.guard.limits.max_body_bytes
        ):
            await self._reject(send, 413, "invalid", "g0_body_too_large")
            return
        if not await self.guard.admit():
            await self._reject(
                send,
                429,
                "retryable_error",
                "g0_rate_limited",
                retry_after=math.ceil(self.guard.limits.rate_window_seconds),
            )
            return

        work = asyncio.create_task(self._buffered_call(scope, receive))
        stopped = asyncio.create_task(self.guard.stop_controller.wait())
        done, _ = await asyncio.wait(
            {work, stopped},
            timeout=self.guard.limits.request_timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stopped in done:
            await self._cancel(work)
            await self._reject(send, 503, "disabled", "g0_ingress_stopped")
            return
        if work not in done:
            await self._cancel(work, stopped)
            await self._reject(send, 504, "retryable_error", "g0_request_timeout")
            return

        await self._cancel(stopped)
        try:
            messages = work.result()
        except _BodyTooLarge:
            await self._reject(send, 413, "invalid", "g0_body_too_large")
            return
        except _ClientDisconnected:
            await self._reject(send, 400, "invalid", "g0_client_disconnected")
            return
        except _IngressStopped:
            await self._reject(send, 503, "disabled", "g0_ingress_stopped")
            return
        for message in messages:
            await send(message)

    async def _buffered_call(
        self,
        scope: Scope,
        receive: Receive,
    ) -> list[Message]:
        body = await self._read_body(receive)
        if self.guard.stop_controller.stopped:
            raise _IngressStopped
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        messages: list[Message] = []

        async def capture(message: Message) -> None:
            messages.append(message)

        await self.app(scope, replay, capture)
        return messages

    async def _read_body(self, receive: Receive) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise _ClientDisconnected
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.guard.limits.max_body_bytes:
                raise _BodyTooLarge
            if chunk:
                chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    @staticmethod
    def _content_length(scope: Scope) -> Optional[int]:
        values = [
            value
            for name, value in scope.get("headers", ())
            if name.lower() == b"content-length"
        ]
        if not values:
            return None
        if len(values) != 1:
            raise ValueError("duplicate content-length")
        try:
            length = int(values[0].decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("invalid content-length") from exc
        if length < 0:
            raise ValueError("invalid content-length")
        return length

    @staticmethod
    async def _cancel(*tasks: asyncio.Task) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _reject(
        send: Send,
        status_code: int,
        status: str,
        reason: str,
        *,
        retry_after: Optional[int] = None,
    ) -> None:
        body = json.dumps(
            {
                "status": status,
                "reason": reason,
                "persisted": False,
                "nia_called": False,
                "bitrix_written": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
        ]
        if retry_after is not None:
            headers.append((b"retry-after", str(retry_after).encode("ascii")))
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})


__all__ = [
    "G0IngressGuard",
    "G0IngressGuardMiddleware",
    "G0IngressLimits",
    "G0StopController",
]
