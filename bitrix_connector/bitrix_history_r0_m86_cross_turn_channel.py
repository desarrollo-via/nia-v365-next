"""M86-D: canal allowlisted entre turnos, one-shot y con expiración."""

from __future__ import annotations

import json
import math
import os
import time
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .bitrix_history_r0_m85_final_command_rehearsal import (
    M85_MANUAL_REMOVAL_TEXT,
    M85_SECOND_CONFIRMATION_TEXT,
)


M86_CHANNEL_SCHEMA = "nia-next-r1-cross-turn-v1"
M86_CHANNEL_FILENAME = "m86_r1_channel_v1.json"
M86_CHANNEL_LOCK_FILENAME = "m86_r1_channel_v1.lock"
M86_CHANNEL_TEMP_FILENAME = "m86_r1_channel_v1.tmp"
M86_CHANNEL_MAX_TTL_SECONDS = 300.0
M86_CHANNEL_MAX_BYTES = 1024


class M86ChannelStage(str, Enum):
    AWAITING_MANUAL_REMOVAL = "AWAITING_MANUAL_REMOVAL"
    AWAITING_SECOND_CONFIRMATION = "AWAITING_SECOND_CONFIRMATION"
    READY_FOR_WAITING_MESSAGE = "READY_FOR_WAITING_MESSAGE"
    WAITING_MESSAGE = "WAITING-MESSAGE"
    MESSAGE_SENT = "MESSAGE-SENT-CONFIRMED"


_STAGE_SEQUENCE = {
    M86ChannelStage.AWAITING_MANUAL_REMOVAL: 1,
    M86ChannelStage.AWAITING_SECOND_CONFIRMATION: 2,
    M86ChannelStage.READY_FOR_WAITING_MESSAGE: 3,
    M86ChannelStage.WAITING_MESSAGE: 4,
    M86ChannelStage.MESSAGE_SENT: 5,
}


class M86ChannelAction(str, Enum):
    OPEN_AFTER_PREFLIGHT = "OPEN_AFTER_PREFLIGHT"
    CONFIRM_MANUAL_REMOVAL = "CONFIRM_MANUAL_REMOVAL"
    CONFIRM_SECOND_EXECUTION = "CONFIRM_SECOND_EXECUTION"
    MARK_WAITING_MESSAGE = "MARK_WAITING_MESSAGE"
    CONFIRM_MESSAGE_SENT = "CONFIRM_MESSAGE_SENT"
    CONSUME_WAITING_MESSAGE = "CONSUME_WAITING_MESSAGE"
    ABORT = "ABORT"


class M86ChannelRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_name: Literal["nia-next-r1-cross-turn-v1"] = M86_CHANNEL_SCHEMA
    stage: M86ChannelStage
    sequence: int = Field(ge=1, le=5)
    expires_at_unix: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_exact_sequence(self) -> "M86ChannelRecord":
        if (
            self.sequence != _STAGE_SEQUENCE[self.stage]
            or not math.isfinite(self.expires_at_unix)
        ):
            raise ValueError("m86d_channel_record_invalid")
        return self


class M86AllowlistedStateBackend(Protocol):
    def load(self) -> Optional[M86ChannelRecord]: ...

    def save(
        self,
        record: M86ChannelRecord,
        *,
        expected_sequence: Optional[int],
    ) -> None: ...

    def delete(self, *, expected_sequence: Optional[int]) -> None: ...


class InMemoryM86AllowlistedStateBackend:
    __slots__ = ("record", "load_calls", "save_calls", "delete_calls")

    def __init__(self) -> None:
        self.record: Optional[M86ChannelRecord] = None
        self.load_calls = 0
        self.save_calls = 0
        self.delete_calls = 0

    def load(self) -> Optional[M86ChannelRecord]:
        self.load_calls += 1
        return self.record

    def save(
        self,
        record: M86ChannelRecord,
        *,
        expected_sequence: Optional[int],
    ) -> None:
        current_sequence = self.record.sequence if self.record is not None else None
        if current_sequence != expected_sequence:
            raise RuntimeError("m86d_channel_sequence_conflict")
        self.save_calls += 1
        self.record = record

    def delete(self, *, expected_sequence: Optional[int]) -> None:
        current_sequence = self.record.sequence if self.record is not None else None
        if expected_sequence is not None and current_sequence != expected_sequence:
            raise RuntimeError("m86d_channel_sequence_conflict")
        self.delete_calls += 1
        self.record = None


class JsonFileM86AllowlistedStateBackend:
    """Backend atómico exacto; no enumera rutas ni guarda textos humanos."""

    __slots__ = ("_lock_path", "_root", "_state_path", "_temp_path")

    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("m86d_channel_root_invalid")
        self._root = root.resolve()
        self._state_path = self._root / M86_CHANNEL_FILENAME
        self._lock_path = self._root / M86_CHANNEL_LOCK_FILENAME
        self._temp_path = self._root / M86_CHANNEL_TEMP_FILENAME

    def __repr__(self) -> str:
        return "JsonFileM86AllowlistedStateBackend(<redacted>)"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self._lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            raise RuntimeError("m86d_channel_locked") from error
        try:
            os.close(descriptor)
            yield
        finally:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _load_unlocked(self) -> Optional[M86ChannelRecord]:
        if not self._state_path.exists():
            return None
        try:
            payload = self._state_path.read_bytes()
            if not payload or len(payload) > M86_CHANNEL_MAX_BYTES:
                raise ValueError("m86d_channel_file_invalid")
            parsed = json.loads(payload.decode("utf-8"))
            return M86ChannelRecord.model_validate(parsed)
        except (OSError, UnicodeError, ValueError, ValidationError) as error:
            raise RuntimeError("m86d_channel_file_invalid") from error

    def load(self) -> Optional[M86ChannelRecord]:
        with self._lock():
            return self._load_unlocked()

    def save(
        self,
        record: M86ChannelRecord,
        *,
        expected_sequence: Optional[int],
    ) -> None:
        if type(record) is not M86ChannelRecord:
            raise TypeError("m86d_channel_record_type_invalid")
        with self._lock():
            current = self._load_unlocked()
            current_sequence = current.sequence if current is not None else None
            if current_sequence != expected_sequence:
                raise RuntimeError("m86d_channel_sequence_conflict")
            payload = json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(payload) > M86_CHANNEL_MAX_BYTES:
                raise ValueError("m86d_channel_file_invalid")
            if self._temp_path.exists():
                raise RuntimeError("m86d_channel_temp_conflict")
            descriptor: Optional[int] = None
            try:
                descriptor = os.open(
                    self._temp_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(descriptor, "wb", closefd=True) as stream:
                    descriptor = None
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(self._temp_path, self._state_path)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                self._temp_path.unlink(missing_ok=True)

    def delete(self, *, expected_sequence: Optional[int]) -> None:
        with self._lock():
            if expected_sequence is not None:
                current = self._load_unlocked()
                current_sequence = current.sequence if current is not None else None
                if current_sequence != expected_sequence:
                    raise RuntimeError("m86d_channel_sequence_conflict")
            self._state_path.unlink(missing_ok=True)
            self._temp_path.unlink(missing_ok=True)


class M86CrossTurnChannelSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M86-D"] = "M86-D"
    state: Literal[
        "PREPARED",
        "ADVANCED",
        "ATTENTION-REQUIRED",
        "CONSUMED",
        "EXPIRED",
        "NO-GO",
    ]
    reason: str
    action_calls: int = Field(ge=0, le=1)
    load_calls: int = Field(ge=0, le=1)
    save_calls: int = Field(ge=0, le=1)
    delete_calls: int = Field(ge=0, le=1)
    resulting_stage: Optional[M86ChannelStage] = None
    sequence: int = Field(ge=0, le=5)
    literal_verified_in_memory: bool = False
    literal_persisted: Literal[False] = False
    allowlisted_fields_only: Literal[True] = True
    expired_state_cleared: bool = False
    private_state_cleared: bool = False
    retry_budget: Literal[0] = 0
    attention_required_now: bool = False
    human_message_required_now: bool = False
    attention_notification_emitted: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    real_authorizations_consumed: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted_business_data: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    remaining_real_bindings: Literal[1] = 1


Clock = Callable[[], float]


class M86CrossTurnChannel:
    """Cada instancia ejecuta como máximo una transición allowlisted."""

    __slots__ = ("_backend", "_clock", "_execution_enabled", "_used")

    def __init__(
        self,
        *,
        backend: M86AllowlistedStateBackend,
        clock: Clock = time.time,
        execution_enabled: bool = False,
    ) -> None:
        if (
            backend is None
            or not all(
                callable(getattr(backend, name, None))
                for name in ("load", "save", "delete")
            )
            or not callable(clock)
            or type(execution_enabled) is not bool
        ):
            raise TypeError("m86d_channel_dependency_invalid")
        self._backend: Optional[M86AllowlistedStateBackend] = backend
        self._clock: Optional[Clock] = clock
        self._execution_enabled = execution_enabled
        self._used = False

    def __repr__(self) -> str:
        return "M86CrossTurnChannel(<redacted>)"

    @staticmethod
    def _snapshot(
        *,
        state: str,
        reason: str,
        action_calls: int = 0,
        load_calls: int = 0,
        save_calls: int = 0,
        delete_calls: int = 0,
        resulting_stage: Optional[M86ChannelStage] = None,
        sequence: int = 0,
        literal_verified_in_memory: bool = False,
        expired_state_cleared: bool = False,
        private_state_cleared: bool = False,
        attention_required_now: bool = False,
    ) -> M86CrossTurnChannelSnapshot:
        return M86CrossTurnChannelSnapshot(
            state=state,
            reason=reason,
            action_calls=action_calls,
            load_calls=load_calls,
            save_calls=save_calls,
            delete_calls=delete_calls,
            resulting_stage=resulting_stage,
            sequence=sequence,
            literal_verified_in_memory=literal_verified_in_memory,
            expired_state_cleared=expired_state_cleared,
            private_state_cleared=private_state_cleared,
            attention_required_now=attention_required_now,
            human_message_required_now=attention_required_now,
        )

    def preview(self) -> M86CrossTurnChannelSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86d_cross_turn_channel_bound_not_opened",
        )

    def advance_once(
        self,
        *,
        action: M86ChannelAction,
        literal: Optional[str] = None,
        ttl_seconds: float = M86_CHANNEL_MAX_TTL_SECONDS,
    ) -> M86CrossTurnChannelSnapshot:
        if not self._execution_enabled:
            return self.preview()
        if self._used or self._backend is None or self._clock is None:
            self._used = True
            return self._snapshot(
                state="NO-GO",
                reason="m86d_channel_reuse_rejected",
                private_state_cleared=True,
            )
        self._used = True
        backend, self._backend = self._backend, None
        clock, self._clock = self._clock, None
        loads = 0
        saves = 0
        deletes = 0
        current: Optional[M86ChannelRecord] = None
        try:
            if type(action) is not M86ChannelAction:
                raise TypeError("m86d_channel_action_invalid")
            now = clock()
            if type(now) not in (int, float) or not math.isfinite(float(now)):
                raise ValueError("m86d_channel_clock_invalid")
            now = float(now)
            loads = 1
            current = backend.load()
            if current is not None and now >= current.expires_at_unix:
                backend.delete(expected_sequence=current.sequence)
                deletes = 1
                return self._snapshot(
                    state="EXPIRED",
                    reason="m86d_channel_expired_and_cleared",
                    action_calls=1,
                    load_calls=loads,
                    delete_calls=deletes,
                    expired_state_cleared=True,
                    private_state_cleared=True,
                )
            if action is M86ChannelAction.ABORT:
                backend.delete(
                    expected_sequence=current.sequence if current is not None else None
                )
                deletes = 1
                return self._snapshot(
                    state="CONSUMED",
                    reason="m86d_channel_aborted_and_cleared",
                    action_calls=1,
                    load_calls=loads,
                    delete_calls=deletes,
                    private_state_cleared=True,
                )

            literal_verified = False
            if action is M86ChannelAction.OPEN_AFTER_PREFLIGHT:
                if current is not None or literal is not None:
                    raise ValueError("m86d_channel_transition_invalid")
                if (
                    type(ttl_seconds) not in (int, float)
                    or not math.isfinite(float(ttl_seconds))
                    or ttl_seconds <= 0
                    or ttl_seconds > M86_CHANNEL_MAX_TTL_SECONDS
                ):
                    raise ValueError("m86d_channel_ttl_invalid")
                next_record = M86ChannelRecord(
                    stage=M86ChannelStage.AWAITING_MANUAL_REMOVAL,
                    sequence=1,
                    expires_at_unix=now + float(ttl_seconds),
                )
                expected_sequence = None
            elif action is M86ChannelAction.CONFIRM_MANUAL_REMOVAL:
                if (
                    current is None
                    or current.stage is not M86ChannelStage.AWAITING_MANUAL_REMOVAL
                    or type(literal) is not str
                    or literal != M85_MANUAL_REMOVAL_TEXT
                ):
                    raise ValueError("m86d_manual_confirmation_invalid")
                literal_verified = True
                next_record = current.model_copy(
                    update={
                        "stage": M86ChannelStage.AWAITING_SECOND_CONFIRMATION,
                        "sequence": 2,
                    }
                )
                expected_sequence = current.sequence
            elif action is M86ChannelAction.CONFIRM_SECOND_EXECUTION:
                if (
                    current is None
                    or current.stage is not M86ChannelStage.AWAITING_SECOND_CONFIRMATION
                    or type(literal) is not str
                    or literal != M85_SECOND_CONFIRMATION_TEXT
                ):
                    raise ValueError("m86d_second_confirmation_invalid")
                literal_verified = True
                next_record = current.model_copy(
                    update={
                        "stage": M86ChannelStage.READY_FOR_WAITING_MESSAGE,
                        "sequence": 3,
                    }
                )
                expected_sequence = current.sequence
            elif action is M86ChannelAction.MARK_WAITING_MESSAGE:
                if (
                    current is None
                    or current.stage is not M86ChannelStage.READY_FOR_WAITING_MESSAGE
                    or literal is not None
                ):
                    raise ValueError("m86d_waiting_transition_invalid")
                next_record = current.model_copy(
                    update={
                        "stage": M86ChannelStage.WAITING_MESSAGE,
                        "sequence": 4,
                    }
                )
                expected_sequence = current.sequence
            elif action is M86ChannelAction.CONFIRM_MESSAGE_SENT:
                if (
                    current is None
                    or current.stage is not M86ChannelStage.WAITING_MESSAGE
                    or literal is not None
                ):
                    raise ValueError("m86d_message_sent_transition_invalid")
                next_record = current.model_copy(
                    update={
                        "stage": M86ChannelStage.MESSAGE_SENT,
                        "sequence": 5,
                    }
                )
                expected_sequence = current.sequence
            elif action is M86ChannelAction.CONSUME_WAITING_MESSAGE:
                if (
                    current is None
                    or current.stage not in (
                        M86ChannelStage.WAITING_MESSAGE,
                        M86ChannelStage.MESSAGE_SENT,
                    )
                    or literal is not None
                ):
                    raise ValueError("m86d_waiting_consume_invalid")
                backend.delete(expected_sequence=current.sequence)
                deletes = 1
                return self._snapshot(
                    state="CONSUMED",
                    reason="m86d_waiting_state_consumed_and_cleared",
                    action_calls=1,
                    load_calls=loads,
                    delete_calls=deletes,
                    sequence=current.sequence,
                    private_state_cleared=True,
                )
            else:  # pragma: no cover - Enum exhaustivo
                raise ValueError("m86d_channel_action_invalid")

            backend.save(next_record, expected_sequence=expected_sequence)
            saves = 1
            attention = next_record.stage is M86ChannelStage.WAITING_MESSAGE
            return self._snapshot(
                state="ATTENTION-REQUIRED" if attention else "ADVANCED",
                reason=(
                    "m86d_waiting_message_attention_boundary_reached"
                    if attention
                    else "m86d_channel_stage_advanced"
                ),
                action_calls=1,
                load_calls=loads,
                save_calls=saves,
                resulting_stage=next_record.stage,
                sequence=next_record.sequence,
                literal_verified_in_memory=literal_verified,
                attention_required_now=attention,
            )
        except BaseException:
            try:
                backend.delete(
                    expected_sequence=current.sequence if current is not None else None
                )
                deletes = 1
                cleared = True
            except BaseException:
                cleared = False
            return self._snapshot(
                state="NO-GO",
                reason=(
                    "m86d_channel_failed_safe"
                    if cleared
                    else "m86d_channel_cleanup_failed"
                ),
                action_calls=1,
                load_calls=loads,
                save_calls=saves,
                delete_calls=deletes,
                private_state_cleared=cleared,
            )


def build_real_m86_cross_turn_channel() -> M86CrossTurnChannel:
    """Enlaza el archivo local exacto sin crear directorio ni estado."""

    runtime_root = Path(__file__).resolve().parent.parent / ".runtime"
    return M86CrossTurnChannel(
        backend=JsonFileM86AllowlistedStateBackend(root=runtime_root),
        execution_enabled=False,
    )


__all__ = [
    "InMemoryM86AllowlistedStateBackend",
    "JsonFileM86AllowlistedStateBackend",
    "M86AllowlistedStateBackend",
    "M86ChannelAction",
    "M86ChannelRecord",
    "M86ChannelStage",
    "M86CrossTurnChannel",
    "M86CrossTurnChannelSnapshot",
    "M86_CHANNEL_FILENAME",
    "M86_CHANNEL_LOCK_FILENAME",
    "M86_CHANNEL_MAX_TTL_SECONDS",
    "M86_CHANNEL_SCHEMA",
    "M86_CHANNEL_TEMP_FILENAME",
    "build_real_m86_cross_turn_channel",
]
