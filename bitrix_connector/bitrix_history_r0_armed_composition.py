"""Composición diferida y protegida del lector R0 armado."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Optional

from .bitrix_history_r0_client import BitrixHistoryR0Client
from .bitrix_history_r0_preflight import BitrixHistoryR0Anchor
from .bitrix_history_r0_preflight_composition import (
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    StoredOAuthResources,
    StoredOAuthResourcesFactory,
)
from .bitrix_history_r0_runner import (
    ABSOLUTE_MAX_WAIT_SECONDS,
    STANDARD_POLL_SECONDS,
    STANDARD_WAIT_SECONDS,
    BitrixHistoryReader,
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
    WaitingMessageSignal,
    _barriers_safe,
    _ignore_waiting_message,
    execute_bitrix_history_r0_from_anchor_once,
)
from .config import ConnectorSettings
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HistoryClientBuilder = Callable[..., BitrixHistoryReader]


@dataclass(frozen=True, repr=False)
class BitrixHistoryR0EphemeralInputs:
    """Entradas no persistidas para identificar un único mensaje controlado."""

    expected_text_sha256: str
    window_start: datetime
    wait_seconds: int = STANDARD_WAIT_SECONDS
    poll_seconds: int = STANDARD_POLL_SECONDS

    def __post_init__(self) -> None:
        digest = self.expected_text_sha256.strip().lower()
        if not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError("bitrix_history_expected_hash_invalid")
        if (
            self.window_start.tzinfo is None
            or self.window_start.utcoffset() is None
        ):
            raise ValueError("bitrix_history_window_invalid")
        if (
            self.wait_seconds <= 0
            or self.wait_seconds > ABSOLUTE_MAX_WAIT_SECONDS
            or self.poll_seconds < STANDARD_POLL_SECONDS
        ):
            raise ValueError("bitrix_history_window_invalid")
        object.__setattr__(self, "expected_text_sha256", digest)

    def __repr__(self) -> str:
        return "BitrixHistoryR0EphemeralInputs(<redacted>)"


class _OwnedHistoryReader:
    """Cierra el cliente HTTP y luego los recursos OAuth/Mongo propietarios."""

    def __init__(
        self,
        client: BitrixHistoryReader,
        resources: StoredOAuthResources,
    ) -> None:
        self._client = client
        self._resources = resources

    async def get_dialog(self, dialog_id: str):
        return await self._client.get_dialog(dialog_id)

    async def get_session_history(self, session_id: int):
        return await self._client.get_session_history(session_id)

    async def close(self) -> None:
        first_error: Optional[BaseException] = None
        try:
            await self._client.close()
        except BaseException as exc:
            first_error = exc
        try:
            await self._resources.close()
        except BaseException as exc:
            first_error = first_error or exc
        if first_error is not None:
            raise first_error


def _blocked(reason: str, *, resources_closed: bool = True) -> BitrixHistoryR0Result:
    return BitrixHistoryR0Result(
        status=BitrixHistoryR0Status.NO_GO,
        reason=reason,
        dialog_read_calls=0,
        history_read_calls=0,
        resources_closed=resources_closed,
    )


class StoredOAuthHistoryArmedReader:
    """Construye y consume el lector protegido una sola vez después del armado."""

    __slots__ = (
        "_client_builder",
        "_inputs",
        "_on_waiting_message",
        "_resources_factory",
        "_settings",
        "_sleep",
        "_timeout_seconds",
        "_used",
    )

    def __init__(
        self,
        *,
        settings: ConnectorSettings,
        inputs: BitrixHistoryR0EphemeralInputs,
        timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
        resources_factory: Optional[StoredOAuthResourcesFactory] = None,
        client_builder: HistoryClientBuilder = BitrixHistoryR0Client,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_waiting_message: WaitingMessageSignal = _ignore_waiting_message,
    ) -> None:
        self._settings = settings
        self._inputs = inputs
        self._timeout_seconds = timeout_seconds
        self._resources_factory = resources_factory
        self._client_builder = client_builder
        self._sleep = sleep
        self._on_waiting_message = on_waiting_message
        self._used = False

    def __repr__(self) -> str:
        return "StoredOAuthHistoryArmedReader(<redacted>)"

    async def __call__(
        self,
        anchor: BitrixHistoryR0Anchor,
    ) -> BitrixHistoryR0Result:
        if self._used:
            return _blocked("bitrix_history_armed_reader_already_used")
        self._used = True
        if not _barriers_safe(self._settings):
            return _blocked("bitrix_history_barrier_degraded")
        if (
            self._timeout_seconds <= 0
            or self._timeout_seconds > DEFAULT_PREFLIGHT_TIMEOUT_SECONDS
        ):
            return _blocked("bitrix_history_timeout_invalid")

        resources: Optional[StoredOAuthResources] = None
        try:
            selected_factory = (
                self._resources_factory or PilotDiscoveryOAuthFactory()
            )
            resources = await selected_factory.build(
                self._settings,
                timeout_seconds=self._timeout_seconds,
            )
            access_token = await resources.oauth_provider.get_access_token(
                resources.member_id
            )
            client = self._client_builder(
                portal_url=resources.portal_url,
                access_token=access_token,
                timeout_seconds=self._timeout_seconds,
            )
            owned_reader = _OwnedHistoryReader(client, resources)
            resources = None
            return await execute_bitrix_history_r0_from_anchor_once(
                anchor=anchor,
                client=owned_reader,
                settings=self._settings,
                expected_text_sha256=self._inputs.expected_text_sha256,
                window_start=self._inputs.window_start,
                wait_seconds=self._inputs.wait_seconds,
                poll_seconds=self._inputs.poll_seconds,
                sleep=self._sleep,
                on_waiting_message=self._on_waiting_message,
            )
        except asyncio.CancelledError:
            if resources is not None:
                await resources.close()
            raise
        except Exception:
            resources_closed = True
            if resources is not None:
                try:
                    await resources.close()
                except Exception:
                    resources_closed = False
            return _blocked(
                (
                    "bitrix_history_armed_reader_failed_safe"
                    if resources_closed
                    else "bitrix_history_resources_close_failed"
                ),
                resources_closed=resources_closed,
            )


def compose_stored_oauth_history_armed_reader(
    *,
    settings: ConnectorSettings,
    inputs: BitrixHistoryR0EphemeralInputs,
    timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    resources_factory: Optional[StoredOAuthResourcesFactory] = None,
    client_builder: HistoryClientBuilder = BitrixHistoryR0Client,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_waiting_message: WaitingMessageSignal = _ignore_waiting_message,
) -> StoredOAuthHistoryArmedReader:
    """Compone sin abrir recursos; la construcción real queda diferida al hook."""

    return StoredOAuthHistoryArmedReader(
        settings=settings,
        inputs=inputs,
        timeout_seconds=timeout_seconds,
        resources_factory=resources_factory,
        client_builder=client_builder,
        sleep=sleep,
        on_waiting_message=on_waiting_message,
    )


__all__ = [
    "BitrixHistoryR0EphemeralInputs",
    "HistoryClientBuilder",
    "StoredOAuthHistoryArmedReader",
    "compose_stored_oauth_history_armed_reader",
]
