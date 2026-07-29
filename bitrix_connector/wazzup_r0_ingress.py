"""Ingreso ASGI hermetico y desmontado para el adaptador Wazzup R0."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .wazzup_r0_adapter import (
    InMemoryWazzupR0Adapter,
    WazzupHeaderVerifier,
    WazzupR0AdapterMountStatus,
    WazzupR0Observation,
    WazzupR0ObservationStatus,
    WazzupR0Scope,
    build_optional_wazzup_r0_adapter,
)


WAZZUP_R0_INGRESS_PATH = "/bitrix-connector/internal/wazzup-r0"


@dataclass(frozen=True)
class WazzupR0IngressLimits:
    max_body_bytes: int = 65_536
    max_body_chunks: int = 64
    request_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.max_body_bytes < 1 or self.max_body_bytes > 1_048_576:
            raise ValueError("wazzup_r0_max_body_bytes_invalid")
        if self.max_body_chunks < 1 or self.max_body_chunks > 1_024:
            raise ValueError("wazzup_r0_max_body_chunks_invalid")
        if (
            self.request_timeout_seconds <= 0
            or self.request_timeout_seconds > 30
        ):
            raise ValueError("wazzup_r0_request_timeout_invalid")


@dataclass(frozen=True)
class WazzupR0IngressMount:
    enabled: bool
    status: WazzupR0AdapterMountStatus
    reason: str
    app: Optional[ASGIApp] = None


class _BodyTooLarge(Exception):
    pass


class _TooManyChunks(Exception):
    pass


class _ClientDisconnected(Exception):
    pass


class WazzupR0IngressApp:
    """Callable ASGI sin servidor, router, entorno global ni recursos externos."""

    def __init__(
        self,
        *,
        adapter: InMemoryWazzupR0Adapter,
        header_verifier: WazzupHeaderVerifier,
        limits: WazzupR0IngressLimits = WazzupR0IngressLimits(),
    ) -> None:
        self._adapter = adapter
        self._header_verifier = header_verifier
        self._limits = limits

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope.get("type") != "http":
            return
        if scope.get("path") != WAZZUP_R0_INGRESS_PATH:
            await self._fixed_response(send, 404, "wazzup_r0_route_not_found")
            return
        if scope.get("method") != "POST":
            await self._fixed_response(send, 405, "wazzup_r0_method_not_allowed")
            return

        try:
            headers = self._headers(scope)
        except ValueError:
            await self._fixed_response(send, 400, "wazzup_r0_headers_invalid")
            return

        # Esta comprobacion ocurre deliberadamente antes del primer receive().
        try:
            authenticated = bool(self._header_verifier(headers))
        except Exception:
            await self._fixed_response(send, 503, "wazzup_r0_auth_unavailable")
            return
        if not authenticated:
            await self._fixed_response(send, 401, "wazzup_r0_unauthorized")
            return

        try:
            declared_length = self._content_length(headers)
        except ValueError:
            await self._fixed_response(send, 400, "wazzup_r0_content_length_invalid")
            return
        if (
            declared_length is not None
            and declared_length > self._limits.max_body_bytes
        ):
            await self._fixed_response(send, 413, "wazzup_r0_body_too_large")
            return

        try:
            observation = await asyncio.wait_for(
                self._observe(receive, headers),
                timeout=self._limits.request_timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._fixed_response(send, 504, "wazzup_r0_request_timeout")
            return
        except _BodyTooLarge:
            await self._fixed_response(send, 413, "wazzup_r0_body_too_large")
            return
        except _TooManyChunks:
            await self._fixed_response(send, 400, "wazzup_r0_too_many_chunks")
            return
        except _ClientDisconnected:
            await self._fixed_response(send, 400, "wazzup_r0_client_disconnected")
            return
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            await self._fixed_response(send, 422, "wazzup_r0_payload_invalid")
            return

        status_code = {
            WazzupR0ObservationStatus.REJECTED: 401,
            WazzupR0ObservationStatus.INVALID: 422,
            WazzupR0ObservationStatus.UNAVAILABLE: 503,
        }.get(observation.status, 200)
        await self._json_response(
            send,
            status_code,
            observation.model_dump(mode="json"),
        )

    async def _observe(
        self,
        receive: Receive,
        headers: Mapping[str, str],
    ) -> WazzupR0Observation:
        body = await self._read_body(receive)
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=self._unique_object,
            parse_constant=self._reject_json_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError("wazzup_r0_payload_not_object")
        # El adaptador vuelve a verificar las mismas cabeceras y falla cerrado.
        return self._adapter.observe(payload, headers=headers)

    async def _read_body(self, receive: Receive) -> bytes:
        chunks: list[bytes] = []
        total = 0
        count = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                raise _ClientDisconnected
            if message.get("type") != "http.request":
                raise _ClientDisconnected
            count += 1
            if count > self._limits.max_body_chunks:
                raise _TooManyChunks
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self._limits.max_body_bytes:
                raise _BodyTooLarge
            if chunk:
                chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    @staticmethod
    def _headers(scope: Scope) -> dict[str, str]:
        headers: dict[str, str] = {}
        for raw_name, raw_value in scope.get("headers", ()):
            try:
                name = raw_name.decode("ascii").lower()
                value = raw_value.decode("latin-1")
            except (UnicodeDecodeError, AttributeError) as exc:
                raise ValueError("wazzup_r0_header_invalid") from exc
            if not name or name in headers:
                raise ValueError("wazzup_r0_header_duplicate")
            headers[name] = value
        return headers

    @staticmethod
    def _content_length(headers: Mapping[str, str]) -> Optional[int]:
        raw_value = headers.get("content-length")
        if raw_value is None:
            return None
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError("wazzup_r0_content_length_invalid") from exc
        if value < 0:
            raise ValueError("wazzup_r0_content_length_invalid")
        return value

    @staticmethod
    def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("wazzup_r0_json_key_duplicate")
            result[key] = value
        return result

    @staticmethod
    def _reject_json_constant(value: str) -> Any:
        raise ValueError("wazzup_r0_json_constant_invalid")

    @classmethod
    async def _fixed_response(
        cls,
        send: Send,
        status_code: int,
        reason: str,
    ) -> None:
        await cls._json_response(
            send,
            status_code,
            {
                "status": "rejected",
                "reason": reason,
                "persisted": False,
                "nia_called": False,
                "bitrix_written": False,
            },
        )

    @staticmethod
    async def _json_response(
        send: Send,
        status_code: int,
        payload: Mapping[str, Any],
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def build_optional_wazzup_r0_ingress(
    environ: Mapping[str, str],
    *,
    scope: Optional[WazzupR0Scope] = None,
    header_verifier: Optional[WazzupHeaderVerifier] = None,
    limits: WazzupR0IngressLimits = WazzupR0IngressLimits(),
    max_seen_events: int = 128,
) -> WazzupR0IngressMount:
    """Devuelve ``app=None`` salvo que toda la composicion local sea valida."""

    adapter_mount = build_optional_wazzup_r0_adapter(
        environ,
        scope=scope,
        header_verifier=header_verifier,
        max_seen_events=max_seen_events,
    )
    if not adapter_mount.enabled or adapter_mount.adapter is None:
        return WazzupR0IngressMount(
            enabled=False,
            status=adapter_mount.status,
            reason=adapter_mount.reason,
        )
    if header_verifier is None:
        return WazzupR0IngressMount(
            enabled=False,
            status=WazzupR0AdapterMountStatus.UNAVAILABLE,
            reason="wazzup_r0_ingress_configuration_incomplete",
        )
    return WazzupR0IngressMount(
        enabled=True,
        status=WazzupR0AdapterMountStatus.READY,
        reason="wazzup_r0_ingress_ready_local_only",
        app=WazzupR0IngressApp(
            adapter=adapter_mount.adapter,
            header_verifier=header_verifier,
            limits=limits,
        ),
    )


__all__ = [
    "WAZZUP_R0_INGRESS_PATH",
    "WazzupR0IngressApp",
    "WazzupR0IngressLimits",
    "WazzupR0IngressMount",
    "build_optional_wazzup_r0_ingress",
]
