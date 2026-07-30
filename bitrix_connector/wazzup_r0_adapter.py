"""Adaptador hermético Wazzup v3 para ensayos R0 exclusivamente inertes."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    model_validator,
)


WAZZUP_R0_ADAPTER_SWITCH = "NIA_WAZZUP_R0_ADAPTER_ENABLED"
_SAFE_ID_PATTERN = r"^[^\s\x00-\x1f\x7f]{1,128}$"


class WazzupV3Message(BaseModel):
    """Allowlist mínima del elemento ``messages`` documentado por Wazzup v3."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        populate_by_name=True,
    )

    message_id: str = Field(alias="messageId", pattern=_SAFE_ID_PATTERN)
    channel_id: str = Field(alias="channelId", pattern=_SAFE_ID_PATTERN)
    chat_type: str = Field(
        alias="chatType",
        pattern=r"^[a-z0-9_-]{1,32}$",
    )
    chat_id: str = Field(alias="chatId", pattern=_SAFE_ID_PATTERN)
    date_time: str = Field(alias="dateTime", min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=32)
    text: Optional[SecretStr] = Field(default=None, exclude=True)
    content_uri: Optional[SecretStr] = Field(
        default=None,
        alias="contentUri",
        exclude=True,
    )
    is_echo: bool = Field(default=False, alias="isEcho")

    @model_validator(mode="after")
    def require_content(self) -> "WazzupV3Message":
        text = self.text.get_secret_value() if self.text is not None else ""
        content_uri = (
            self.content_uri.get_secret_value()
            if self.content_uri is not None
            else ""
        )
        if not text and not content_uri:
            raise ValueError("wazzup_r0_content_missing")
        return self


class WazzupV3Envelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    messages: tuple[WazzupV3Message, ...] = Field(
        min_length=1,
        max_length=20,
    )


class WazzupR0Scope(BaseModel):
    """Identidad Wazzup; nunca reutiliza identificadores del chat Bitrix."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_id: str = Field(pattern=_SAFE_ID_PATTERN)
    chat_type: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    chat_id: str = Field(pattern=_SAFE_ID_PATTERN)

    def matches(self, message: WazzupV3Message) -> bool:
        return (
            message.channel_id == self.channel_id
            and message.chat_type == self.chat_type
            and message.chat_id == self.chat_id
        )


class WazzupR0ObservationStatus(str, Enum):
    OBSERVED = "observed"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"
    REJECTED = "rejected"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class WazzupR0Observation(BaseModel):
    """Recibo seguro: no contiene texto, adjuntos, URI ni cabeceras."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WazzupR0ObservationStatus
    reason: str
    event_key: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    message_id: Optional[str] = None
    channel_id: Optional[str] = None
    chat_type: Optional[str] = None
    chat_id: Optional[str] = None
    text_length: int = Field(default=0, ge=0)
    identity_verified: bool = False
    duplicate: bool = False
    persisted: bool = False
    nia_called: bool = False
    bitrix_written: bool = False


WazzupHeaderVerifier = Callable[[Mapping[str, str]], bool]


def _event_key(message: WazzupV3Message) -> str:
    canonical = json.dumps(
        {
            "channel_id": message.channel_id,
            "chat_id": message.chat_id,
            "chat_type": message.chat_type,
            "date_time": message.date_time,
            "message_id": message.message_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InMemoryWazzupR0Adapter:
    """Observa un único mensaje exacto sin persistir ni llamar servicios."""

    def __init__(
        self,
        *,
        scope: WazzupR0Scope,
        header_verifier: WazzupHeaderVerifier,
        max_seen_events: int = 128,
    ) -> None:
        if max_seen_events < 1 or max_seen_events > 10_000:
            raise ValueError("wazzup_r0_seen_limit_invalid")
        self._scope = scope
        self._header_verifier = header_verifier
        self._max_seen_events = max_seen_events
        self._seen: OrderedDict[str, None] = OrderedDict()

    def observe(
        self,
        payload: Any,
        *,
        headers: Mapping[str, str],
    ) -> WazzupR0Observation:
        try:
            authenticated = bool(self._header_verifier(headers))
        except Exception:
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.UNAVAILABLE,
                reason="wazzup_r0_auth_unavailable",
            )
        if not authenticated:
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.REJECTED,
                reason="wazzup_r0_unauthorized",
            )

        try:
            envelope = WazzupV3Envelope.model_validate(payload)
        except (TypeError, ValueError, ValidationError):
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.INVALID,
                reason="wazzup_r0_payload_invalid",
            )
        if len(envelope.messages) != 1:
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.INVALID,
                reason="wazzup_r0_batch_unsupported",
            )

        message = envelope.messages[0]
        if message.status != "inbound" or message.is_echo:
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.IGNORED,
                reason="wazzup_r0_not_inbound",
            )
        if not self._scope.matches(message):
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.IGNORED,
                reason="wazzup_r0_outside_scope",
            )

        event_key = _event_key(message)
        text = message.text.get_secret_value() if message.text is not None else ""
        common = {
            "event_key": event_key,
            "message_id": message.message_id,
            "channel_id": message.channel_id,
            "chat_type": message.chat_type,
            "chat_id": message.chat_id,
            "text_length": len(text),
            "identity_verified": True,
        }
        if event_key in self._seen:
            self._seen.move_to_end(event_key)
            return WazzupR0Observation(
                status=WazzupR0ObservationStatus.DUPLICATE,
                reason="wazzup_r0_duplicate",
                duplicate=True,
                **common,
            )

        self._seen[event_key] = None
        while len(self._seen) > self._max_seen_events:
            self._seen.popitem(last=False)
        return WazzupR0Observation(
            status=WazzupR0ObservationStatus.OBSERVED,
            reason="connector_locked_off",
            **common,
        )


class WazzupR0AdapterMountStatus(str, Enum):
    DISABLED = "disabled"
    READY = "ready"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class WazzupR0AdapterMount:
    enabled: bool
    status: WazzupR0AdapterMountStatus
    reason: str
    adapter: Optional[InMemoryWazzupR0Adapter] = None


def build_optional_wazzup_r0_adapter(
    environ: Mapping[str, str],
    *,
    scope: Optional[WazzupR0Scope] = None,
    header_verifier: Optional[WazzupHeaderVerifier] = None,
    max_seen_events: int = 128,
) -> WazzupR0AdapterMount:
    """Compone el adaptador sin leer entorno global ni crear una ruta HTTP."""

    raw_switch = environ.get(WAZZUP_R0_ADAPTER_SWITCH, "")
    normalized_switch = raw_switch.strip().lower()
    if normalized_switch in {"", "false"}:
        return WazzupR0AdapterMount(
            enabled=False,
            status=WazzupR0AdapterMountStatus.DISABLED,
            reason="wazzup_r0_adapter_disabled",
        )
    if normalized_switch != "true":
        return WazzupR0AdapterMount(
            enabled=False,
            status=WazzupR0AdapterMountStatus.UNAVAILABLE,
            reason="wazzup_r0_adapter_switch_invalid",
        )
    if scope is None or header_verifier is None:
        return WazzupR0AdapterMount(
            enabled=False,
            status=WazzupR0AdapterMountStatus.UNAVAILABLE,
            reason="wazzup_r0_adapter_configuration_incomplete",
        )
    try:
        adapter = InMemoryWazzupR0Adapter(
            scope=scope,
            header_verifier=header_verifier,
            max_seen_events=max_seen_events,
        )
    except ValueError:
        return WazzupR0AdapterMount(
            enabled=False,
            status=WazzupR0AdapterMountStatus.UNAVAILABLE,
            reason="wazzup_r0_adapter_configuration_invalid",
        )
    return WazzupR0AdapterMount(
        enabled=True,
        status=WazzupR0AdapterMountStatus.READY,
        reason="wazzup_r0_adapter_ready_local_only",
        adapter=adapter,
    )


__all__ = [
    "InMemoryWazzupR0Adapter",
    "WAZZUP_R0_ADAPTER_SWITCH",
    "WazzupR0AdapterMount",
    "WazzupR0AdapterMountStatus",
    "WazzupR0Observation",
    "WazzupR0ObservationStatus",
    "WazzupR0Scope",
    "WazzupV3Envelope",
    "WazzupV3Message",
    "build_optional_wazzup_r0_adapter",
]
