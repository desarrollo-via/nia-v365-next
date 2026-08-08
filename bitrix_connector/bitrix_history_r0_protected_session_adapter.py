"""Puente privado entre el owner protegido y el lector diferido R0."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
    compose_stored_oauth_history_armed_reader,
)
from .bitrix_history_r0_protected_handoff_composition import (
    ProtectedInMemoryHandoffOwner,
    prepare_protected_dotenv_history_handoff_once,
)
from .config import ConnectorSettings
from .bitrix_history_r0_runner import (
    BitrixHistoryR0WaitingMessageSnapshot,
    WaitingMessageSignal,
)


ProtectedOwnerPreparer = Callable[..., object]
ArmedReaderComposer = Callable[..., object]
HistoryClientBuilder = Callable[..., object]


async def _ignore_waiting_message(
    _snapshot: BitrixHistoryR0WaitingMessageSnapshot,
) -> None:
    return None


@dataclass(frozen=True)
class ProtectedHistorySessionAdapterSnapshot:
    state: Literal[
        "PREPARED", "OWNER-READY", "READER-READY", "CLEARED", "NO-GO"
    ] = "PREPARED"
    reason: str = "protected_history_session_adapter_prepared"
    owner_builder_calls: int = 0
    settings_capture_calls: int = 0
    reader_factory_calls: int = 0
    cleanup_calls: int = 0
    settings_retained: bool = False
    owner_retained: bool = False
    external_calls: int = 0


class ProtectedHistorySessionDependencyAdapter:
    """Retiene settings sólo entre owner preparado y lector ya armado."""

    __slots__ = (
        "_armed_reader_composer",
        "_cleanup_calls",
        "_dotenv_path",
        "_inputs",
        "_owner",
        "_owner_builder_calls",
        "_owner_preparer",
        "_on_waiting_message",
        "_preflight_client_builder",
        "_reader_client_builder",
        "_reader_factory_calls",
        "_resources_factory",
        "_settings",
        "_settings_capture_calls",
        "_timeout_seconds",
    )

    def __init__(
        self,
        *,
        dotenv_path: Path,
        inputs: BitrixHistoryR0EphemeralInputs,
        resources_factory: object,
        preflight_client_builder: HistoryClientBuilder,
        reader_client_builder: HistoryClientBuilder,
        timeout_seconds: float,
        owner_preparer: ProtectedOwnerPreparer,
        armed_reader_composer: ArmedReaderComposer,
        on_waiting_message: WaitingMessageSignal,
    ) -> None:
        self._dotenv_path = Path(dotenv_path)
        self._inputs = inputs
        self._resources_factory = resources_factory
        self._preflight_client_builder = preflight_client_builder
        self._reader_client_builder = reader_client_builder
        self._timeout_seconds = timeout_seconds
        self._owner_preparer = owner_preparer
        self._armed_reader_composer = armed_reader_composer
        self._on_waiting_message = on_waiting_message
        self._settings: ConnectorSettings | None = None
        self._owner: ProtectedInMemoryHandoffOwner | None = None
        self._owner_builder_calls = 0
        self._settings_capture_calls = 0
        self._reader_factory_calls = 0
        self._cleanup_calls = 0

    def __repr__(self) -> str:
        return "ProtectedHistorySessionDependencyAdapter(<redacted>)"

    def snapshot(self) -> ProtectedHistorySessionAdapterSnapshot:
        if self._cleanup_calls:
            state = "CLEARED"
            reason = "protected_history_session_adapter_cleared"
        elif self._reader_factory_calls:
            state = "READER-READY"
            reason = "protected_history_session_adapter_reader_ready"
        elif self._owner_builder_calls and self._owner is not None:
            state = "OWNER-READY"
            reason = "protected_history_session_adapter_owner_ready"
        elif self._owner_builder_calls:
            state = "NO-GO"
            reason = "protected_history_session_adapter_no_go"
        else:
            state = "PREPARED"
            reason = "protected_history_session_adapter_prepared"
        return ProtectedHistorySessionAdapterSnapshot(
            state=state,
            reason=reason,
            owner_builder_calls=self._owner_builder_calls,
            settings_capture_calls=self._settings_capture_calls,
            reader_factory_calls=self._reader_factory_calls,
            cleanup_calls=self._cleanup_calls,
            settings_retained=self._settings is not None,
            owner_retained=self._owner is not None,
        )

    async def build_owner_once(self) -> ProtectedInMemoryHandoffOwner:
        if self._owner_builder_calls:
            raise RuntimeError("protected_history_session_adapter_owner_already_used")
        self._owner_builder_calls = 1

        def capture_settings(settings: ConnectorSettings) -> None:
            if type(settings) is not ConnectorSettings or self._settings is not None:
                raise TypeError("protected_history_session_adapter_settings_invalid")
            self._settings_capture_calls = 1
            self._settings = settings

        try:
            owner = await self._owner_preparer(
                dotenv_path=self._dotenv_path,
                resources_factory=self._resources_factory,
                client_builder=self._preflight_client_builder,
                timeout_seconds=self._timeout_seconds,
                on_settings_ready=capture_settings,
            )
            if type(owner) is not ProtectedInMemoryHandoffOwner:
                raise TypeError("protected_history_session_adapter_owner_invalid")
            self._owner = owner
            if owner.snapshot().state != "WAITING-AUTHORIZATION":
                self.clear_private_state()
            return owner
        except BaseException:
            self.clear_private_state()
            raise

    def build_reader_once(self):
        if self._reader_factory_calls:
            raise RuntimeError("protected_history_session_adapter_reader_already_used")
        self._reader_factory_calls = 1
        settings = self._settings
        owner = self._owner
        if (
            settings is None
            or owner is None
            or owner.snapshot().state != "ARMED"
        ):
            self.clear_private_state()
            raise RuntimeError("protected_history_session_adapter_not_armed")
        try:
            reader = self._armed_reader_composer(
                settings=settings,
                inputs=self._inputs,
                timeout_seconds=self._timeout_seconds,
                resources_factory=self._resources_factory,
                client_builder=self._reader_client_builder,
                on_waiting_message=self._on_waiting_message,
            )
            if not callable(reader):
                raise TypeError("protected_history_session_adapter_reader_invalid")
            return reader
        finally:
            self._settings = None
            self._owner = None

    def clear_private_state(self) -> None:
        self._cleanup_calls += 1
        self._settings = None
        self._owner = None


def compose_private_protected_history_session_adapter(
    *,
    dotenv_path: Path,
    inputs: BitrixHistoryR0EphemeralInputs,
    resources_factory: object,
    preflight_client_builder: HistoryClientBuilder,
    reader_client_builder: HistoryClientBuilder,
    timeout_seconds: float = 10.0,
    owner_preparer: ProtectedOwnerPreparer = (
        prepare_protected_dotenv_history_handoff_once
    ),
    armed_reader_composer: ArmedReaderComposer = (
        compose_stored_oauth_history_armed_reader
    ),
    on_waiting_message: WaitingMessageSignal = _ignore_waiting_message,
) -> ProtectedHistorySessionDependencyAdapter:
    """Compone closures compatibles con M13 sin abrir fuentes ni recursos."""

    if (
        not str(dotenv_path)
        or type(inputs) is not BitrixHistoryR0EphemeralInputs
        or not callable(getattr(resources_factory, "build", None))
        or not callable(preflight_client_builder)
        or not callable(reader_client_builder)
        or not callable(owner_preparer)
        or not callable(armed_reader_composer)
        or not callable(on_waiting_message)
        or timeout_seconds <= 0
        or timeout_seconds > 10.0
    ):
        raise TypeError("protected_history_session_adapter_dependency_invalid")
    return ProtectedHistorySessionDependencyAdapter(
        dotenv_path=Path(dotenv_path),
        inputs=inputs,
        resources_factory=resources_factory,
        preflight_client_builder=preflight_client_builder,
        reader_client_builder=reader_client_builder,
        timeout_seconds=timeout_seconds,
        owner_preparer=owner_preparer,
        armed_reader_composer=armed_reader_composer,
        on_waiting_message=on_waiting_message,
    )


__all__ = [
    "ArmedReaderComposer",
    "HistoryClientBuilder",
    "ProtectedHistorySessionAdapterSnapshot",
    "ProtectedHistorySessionDependencyAdapter",
    "ProtectedOwnerPreparer",
    "compose_private_protected_history_session_adapter",
]
