"""Fail-closed orchestration for the expired R1 post-write remainder.

This module never resumes the functional EAOR. It validates the persisted
one-write checkpoint locally and attempts closure in safety order:
session/participant, activation, and Key Vault infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Awaitable, Callable, Literal

from .bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from .r1_pre_event_activation_preflight import (
    EXPECTED_BASELINE_VALUES,
    SWITCH_ORDER,
)


LEDGER_KEYS = frozenset({
    "write_budget", "write_reserved", "write_succeeded", "write_used",
})
SurfaceState = Literal["VERIFIED-CLOSED", "NO-GO-REMAINDER"]
RecoveryState = Literal[
    "VERIFIED-RESTORED", "NO-GO-CHECKPOINT", "NO-GO-REMAINDER"
]


@dataclass(frozen=True)
class PostWriteSurfaceCloseResult:
    state: SurfaceState
    resources_closed: bool
    effect_calls: int = 0
    failure_category: str = "none"


@dataclass(frozen=True)
class PostWriteCloseResult:
    state: RecoveryState
    checkpoint_verified: bool
    session_closed: bool
    activation_closed: bool
    key_vault_closed: bool
    closure_attempts: int
    messages_sent: Literal[0] = 0
    secret_write_calls: Literal[0] = 0
    resume_calls: Literal[0] = 0
    failure_surface: str = "none"
    resources_closed: bool = False


def verify_consumed_write_checkpoint(path: Path) -> bool:
    """Accept only the exact successful, fully consumed one-write ledger."""

    if not isinstance(path, Path) or not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(
        type(payload) is dict
        and set(payload) == LEDGER_KEYS
        and all(type(value) is int for value in payload.values())
        and payload == {
            "write_budget": 1,
            "write_reserved": 0,
            "write_succeeded": 1,
            "write_used": 1,
        }
    )


class R1PostWriteCloseRecovery:
    """One-shot closure coordinator; checkpoint audit itself is local-only."""

    __slots__ = (
        "_activation_close", "_key_vault_close", "_ledger_path",
        "_session_close", "_used",
    )

    def __init__(
        self,
        *,
        ledger_path: Path,
        session_close: Callable[[], Awaitable[PostWriteSurfaceCloseResult]],
        activation_close: Callable[[], Awaitable[PostWriteSurfaceCloseResult]],
        key_vault_close: Callable[[], Awaitable[PostWriteSurfaceCloseResult]],
    ) -> None:
        if (
            not isinstance(ledger_path, Path)
            or not all(callable(item) for item in (
                session_close, activation_close, key_vault_close
            ))
        ):
            raise TypeError("r1_post_write_close_dependency_invalid")
        self._ledger_path = ledger_path
        self._session_close = session_close
        self._activation_close = activation_close
        self._key_vault_close = key_vault_close
        self._used = False

    async def close_once(self) -> PostWriteCloseResult:
        if self._used:
            raise RuntimeError("r1_post_write_close_reused")
        self._used = True
        if not verify_consumed_write_checkpoint(self._ledger_path):
            return PostWriteCloseResult(
                state="NO-GO-CHECKPOINT", checkpoint_verified=False,
                session_closed=False, activation_closed=False,
                key_vault_closed=False, closure_attempts=0,
                failure_surface="checkpoint", resources_closed=True,
            )

        operations = (
            ("session", self._session_close),
            ("activation", self._activation_close),
            ("key_vault", self._key_vault_close),
        )
        closed: dict[str, bool] = {}
        attempts = 0
        failure_surface = "none"
        all_resources_closed = True
        for surface, operation in operations:
            attempts += 1
            try:
                result = await operation()
            except BaseException:
                result = PostWriteSurfaceCloseResult(
                    "NO-GO-REMAINDER", False, failure_category="unhandled"
                )
            exact = bool(
                type(result) is PostWriteSurfaceCloseResult
                and result.state == "VERIFIED-CLOSED"
                and result.resources_closed
            )
            closed[surface] = exact
            all_resources_closed = all_resources_closed and bool(
                type(result) is PostWriteSurfaceCloseResult
                and result.resources_closed
            )
            if not exact and failure_surface == "none":
                failure_surface = surface

        verified = all(closed.values()) and all_resources_closed
        return PostWriteCloseResult(
            state="VERIFIED-RESTORED" if verified else "NO-GO-REMAINDER",
            checkpoint_verified=True,
            session_closed=closed["session"],
            activation_closed=closed["activation"],
            key_vault_closed=closed["key_vault"],
            closure_attempts=attempts,
            failure_surface=failure_surface,
            resources_closed=all_resources_closed,
        )

    def __repr__(self) -> str:
        return "R1PostWriteCloseRecovery(<redacted>)"


class R1PostWriteSessionCloser:
    """Status/disarm-only session closer; it never sends confirmations."""

    __slots__ = ("_client", "_used")

    def __init__(self, *, client) -> None:
        if any(not callable(getattr(client, name, None)) for name in (
            "status_once", "disarm_once", "close"
        )):
            raise TypeError("r1_post_write_session_client_invalid")
        self._client = client
        self._used = False

    async def close_once(self) -> PostWriteSurfaceCloseResult:
        if self._used:
            raise RuntimeError("r1_post_write_session_close_reused")
        self._used = True
        client, self._client = self._client, None
        verified = False
        resource_closed = True
        calls = 0
        category = "none"
        try:
            status = await client.status_once()
            calls += 1
            if type(status) is not EventR1ControlSnapshot:
                category = "invalid_status"
            else:
                restored = bool(
                    status.pre_event_lease_state in {
                        "RESTORED", "EXPIRED-RESTORED"
                    }
                    and status.participant_rollback_attempts == 1
                    and status.participant_rollback_verified
                )
                never_armed = bool(
                    status.state == "IDLE"
                    and not status.pre_event_lease_bound
                    and status.participant_arm_attempts == 0
                    and status.participant_rollback_attempts == 0
                    and status.human_message_authorizations == 0
                )
                if restored or never_armed:
                    verified = True
                else:
                    disarmed = await client.disarm_once()
                    calls += 1
                    verified = bool(
                        type(disarmed) is EventR1ControlSnapshot
                        and disarmed.state == "DISARMED"
                        and disarmed.pre_event_lease_state == "RESTORED"
                        and disarmed.participant_rollback_attempts == 1
                        and disarmed.participant_rollback_verified
                    )
                    if not verified:
                        category = "disarm_unverified"
        except BaseException:
            category = "session_unavailable"
        finally:
            try:
                await client.close()
            except BaseException:
                resource_closed = False
        exact = verified and resource_closed
        return PostWriteSurfaceCloseResult(
            "VERIFIED-CLOSED" if exact else "NO-GO-REMAINDER",
            resource_closed, effect_calls=calls,
            failure_category="none" if exact else category,
        )


class R1PostWriteActivationCloser:
    """Restores the known pre-event baseline and verifies dormant state."""

    __slots__ = ("_control", "_used")

    def __init__(self, *, control) -> None:
        required = (
            "restore_exact_switches_once", "restart_after_restore_once",
            "verify_dormant_once", "close",
        )
        if any(not callable(getattr(control, name, None)) for name in required):
            raise TypeError("r1_post_write_activation_control_invalid")
        self._control = control
        self._used = False

    async def close_once(self) -> PostWriteSurfaceCloseResult:
        if self._used:
            raise RuntimeError("r1_post_write_activation_close_reused")
        self._used = True
        control, self._control = self._control, None
        resource_closed = True
        verified = False
        calls = 0
        category = "none"
        rollback_plan = tuple(
            f"restore-value:{name}={EXPECTED_BASELINE_VALUES[name]}"
            for name in SWITCH_ORDER
        )
        try:
            await control.restore_exact_switches_once(rollback_plan)
            calls += 1
            await control.restart_after_restore_once()
            calls += 1
            verified = await control.verify_dormant_once() is True
            calls += 1
            if not verified:
                category = "dormant_unverified"
        except BaseException:
            category = "activation_restore_failed"
        finally:
            try:
                await control.close()
            except BaseException:
                resource_closed = False
        exact = verified and resource_closed
        return PostWriteSurfaceCloseResult(
            "VERIFIED-CLOSED" if exact else "NO-GO-REMAINDER",
            resource_closed, effect_calls=calls,
            failure_category="none" if exact else category,
        )


class R1PostWriteKeyVaultCloser:
    """Read-only verifier for the already-consumed Key Vault checkpoint."""

    __slots__ = ("_used", "_verifier")

    def __init__(self, *, verifier) -> None:
        if any(not callable(getattr(verifier, name, None)) for name in (
            "verify_closed_once", "close"
        )):
            raise TypeError("r1_post_write_key_vault_verifier_invalid")
        self._verifier = verifier
        self._used = False

    async def close_once(self) -> PostWriteSurfaceCloseResult:
        if self._used:
            raise RuntimeError("r1_post_write_key_vault_close_reused")
        self._used = True
        verifier, self._verifier = self._verifier, None
        resource_closed = True
        verified = False
        category = "none"
        try:
            verified = await verifier.verify_closed_once() is True
            if not verified:
                category = "checkpoint_unverified"
        except BaseException:
            category = "checkpoint_unavailable"
        finally:
            try:
                await verifier.close()
            except BaseException:
                resource_closed = False
        exact = verified and resource_closed
        return PostWriteSurfaceCloseResult(
            "VERIFIED-CLOSED" if exact else "NO-GO-REMAINDER",
            resource_closed, effect_calls=1,
            failure_category="none" if exact else category,
        )


__all__ = [
    "PostWriteCloseResult", "PostWriteSurfaceCloseResult",
    "R1PostWriteActivationCloser", "R1PostWriteCloseRecovery",
    "R1PostWriteKeyVaultCloser", "R1PostWriteSessionCloser",
    "verify_consumed_write_checkpoint",
]
