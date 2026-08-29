"""Visor H1 efimero, publico y sin dependencias del conector opcional."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from threading import Lock
from typing import Callable, Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

H1_CHAT_ID = 78733
H1_DIALOG_IDS = frozenset({"78733", "chat78733"})
H1_BOT_ID = 373259
H1_TTL_SECONDS = 30 * 60
H1_ROUTE = "/h1-visible"
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class H1VisibleRecord:
    state: str
    event_key: str
    event: str
    message_id: int
    event_timestamp: Optional[int]
    received_at: datetime
    expires_at: datetime
    bot_id: int
    chat_id: int
    dialog_id: str
    author_id: int
    user_id: int
    text: str


class H1VisibleBuffer:
    def __init__(self, *, ttl_seconds: int = H1_TTL_SECONDS, clock: Clock = _utc_now) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds_must_be_positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._record: Optional[H1VisibleRecord] = None
        self._lock = Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("clock_must_return_timezone_aware_datetime")
        return value.astimezone(timezone.utc)

    async def observe(self, event: object, receipt: object, _settings: object = None) -> None:
        if not all((getattr(event, "event", None) == "ONIMBOTV2MESSAGEADD", getattr(event, "bot_id", None) == H1_BOT_ID, getattr(event, "chat_id", None) == H1_CHAT_ID, getattr(event, "dialog_id", None) in H1_DIALOG_IDS, getattr(event, "message_id", 0) > 0, getattr(event, "author_id", 0) > 0, getattr(event, "user_id", 0) > 0, not getattr(event, "is_system", True), not getattr(event, "user_is_bot", True), not getattr(event, "user_is_connector", True), getattr(receipt, "status", None) == "disabled", getattr(receipt, "reason", None) == "connector_locked_off", getattr(receipt, "identity_verified", False), not getattr(receipt, "persisted", True), not getattr(receipt, "nia_called", True), not getattr(receipt, "bitrix_written", True))):
            return
        now = self._now()
        record = H1VisibleRecord("visible", getattr(receipt, "event_key"), getattr(event, "event"), getattr(event, "message_id"), getattr(event, "timestamp"), now, now + self._ttl, getattr(event, "bot_id"), getattr(event, "chat_id"), getattr(event, "dialog_id"), getattr(event, "author_id"), getattr(event, "user_id"), getattr(event, "text"))
        with self._lock:
            self._record = record

    def snapshot(self) -> Optional[H1VisibleRecord]:
        with self._lock:
            if self._record is not None and self._now() >= self._record.expires_at:
                self._record = None
            return self._record

    def clear(self) -> None:
        with self._lock:
            self._record = None


h1_visible_buffer = H1VisibleBuffer()


def _record_payload(record: H1VisibleRecord) -> dict[str, object]:
    payload = asdict(record)
    payload["received_at"] = record.received_at.isoformat()
    payload["expires_at"] = record.expires_at.isoformat()
    return payload


def _json_payload(buffer: H1VisibleBuffer) -> dict[str, object]:
    record = buffer.snapshot()
    return {"status": "visible" if record else "empty", "ttl_seconds": buffer.ttl_seconds, "record": _record_payload(record) if record else None}


def create_h1_visible_router(buffer: H1VisibleBuffer = h1_visible_buffer) -> APIRouter:
    router = APIRouter()
    no_store = {"Cache-Control": "no-store"}

    @router.get(f"{H1_ROUTE}.json")
    async def h1_visible_json() -> JSONResponse:
        return JSONResponse(_json_payload(buffer), headers=no_store)

    @router.get(H1_ROUTE, response_class=HTMLResponse)
    async def h1_visible_html() -> HTMLResponse:
        record = _json_payload(buffer)["record"]
        body = '<p id="h1-status">Sin mensaje vigente.</p>' if not isinstance(record, dict) else '<p id="h1-status">Mensaje vigente</p><table>' + ''.join(f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>" for key, value in record.items()) + '</table>'
        return HTMLResponse('<!doctype html><html lang="es"><head><meta charset="utf-8"><title>H1 Recepcion visible</title></head><body><h1>H1 Recepcion visible</h1>' + body + '</body></html>', headers={**no_store, "Content-Security-Policy": "default-src 'none'", "X-Content-Type-Options": "nosniff"})

    return router
