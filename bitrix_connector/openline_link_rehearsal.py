"""Ensayo hermetico de vinculacion temporal con rollback obligatorio."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .config import ConnectorSettings
from .openline_pilot_preflight import (
    BITRIX_OPENLINE_CONFIG_UPDATE_METHOD,
    ControlledPilotPreview,
    OpenLineConfigSnapshot,
    OpenLineUpdatePreview,
)
from .openline_r0_receipt import (
    ControlledR0Receipt,
    MAX_R0_RECEIPT_WAIT_SECONDS,
    receipt_is_exact,
)


CONTROLLED_BOT_ID = 373259
CONTROLLED_CHAT_ID = 78733
CONTROLLED_DIALOG_ID = "chat78733"
CONTROLLED_CONFIG_ID = 13
ORIGINAL_WELCOME_BOT_ID = 245339


class OffProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effective_mode: str
    activation_locked: bool
    external_calls_enabled: bool
    identity_verified: bool
    persisted: bool
    nia_called: bool
    bitrix_written: bool


class LinkRehearsalStatus(str, Enum):
    RESTORED = "restored"
    BLOCKED = "blocked"
    FAILED_RESTORED = "failed_restored"
    ROLLBACK_FAILED = "rollback_failed"


class LinkRehearsalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: LinkRehearsalStatus
    reason: str
    config_id: int = CONTROLLED_CONFIG_ID
    controlled_bot_id: int = CONTROLLED_BOT_ID
    original_bot_id: int = ORIGINAL_WELCOME_BOT_ID
    link_attempts: int = Field(default=0, ge=0, le=1)
    rollback_attempts: int = Field(default=0, ge=0, le=1)
    link_verified: bool = False
    off_verified: bool = False
    receipt_verified: bool = False
    rollback_verified: bool = False


def _welcome_values(snapshot: OpenLineConfigSnapshot) -> dict[str, object]:
    return {
        "WELCOME_BOT_ENABLE": snapshot.welcome_bot_enable,
        "WELCOME_BOT_JOIN": snapshot.welcome_bot_join,
        "WELCOME_BOT_ID": snapshot.welcome_bot_id,
        "WELCOME_BOT_TIME": snapshot.welcome_bot_time,
        "WELCOME_BOT_LEFT": snapshot.welcome_bot_left,
    }


def _preview_values(preview: OpenLineUpdatePreview) -> dict[str, object]:
    return preview.payload.PARAMS.model_dump(mode="json")


def _snapshot_is_original(snapshot: OpenLineConfigSnapshot) -> bool:
    return bool(
        snapshot.config_id == CONTROLLED_CONFIG_ID
        and snapshot.active == "Y"
        and snapshot.welcome_bot_enable == "Y"
        and snapshot.welcome_bot_join == "always"
        and snapshot.welcome_bot_id == ORIGINAL_WELCOME_BOT_ID
        and snapshot.welcome_bot_time == 0
        and snapshot.welcome_bot_left == "close"
        and snapshot.no_answer_bot_id == 0
        and snapshot.close_bot_id == 0
        and snapshot.auto_close_bot_id == 0
        and snapshot.worktime_dayoff_bot_id == 0
    )


def _probe_is_off(probe: OffProbeResult) -> bool:
    return bool(
        probe.effective_mode == "off"
        and probe.activation_locked
        and not probe.external_calls_enabled
        and probe.identity_verified
        and not probe.persisted
        and not probe.nia_called
        and not probe.bitrix_written
    )


def _validate_contract(
    *,
    preview: ControlledPilotPreview,
    settings: ConnectorSettings,
    expected_member_id: str,
    now: datetime,
) -> Optional[str]:
    if (
        settings.effective_mode.value != "off"
        or not settings.activation_locked
        or settings.external_calls_enabled
    ):
        return "link_rehearsal_safety_barriers_invalid"
    if now.tzinfo is None or now.utcoffset() is None:
        return "link_rehearsal_clock_not_aware"
    member_id = expected_member_id.strip()
    rule = preview.allowlist
    if (
        not member_id
        or rule.member_id != member_id
        or rule.bot_id != CONTROLLED_BOT_ID
        or rule.chat_id != CONTROLLED_CHAT_ID
        or rule.dialog_id != CONTROLLED_DIALOG_ID
        or rule.valid_from is None
        or rule.valid_until is None
        or not rule.valid_from <= now <= rule.valid_until
    ):
        return "link_rehearsal_scope_or_window_invalid"
    for update in (preview.link, preview.rollback):
        if (
            update.method != BITRIX_OPENLINE_CONFIG_UPDATE_METHOD
            or update.executable
            or update.payload.CONFIG_ID != CONTROLLED_CONFIG_ID
        ):
            return "link_rehearsal_update_contract_invalid"
    if (
        preview.link.payload.PARAMS.WELCOME_BOT_ID != CONTROLLED_BOT_ID
        or preview.rollback.payload.PARAMS.WELCOME_BOT_ID
        != ORIGINAL_WELCOME_BOT_ID
        or preview.impact_scope != "open_line_global"
        or not preview.requires_special_attention
    ):
        return "link_rehearsal_update_contract_invalid"
    return None


async def rehearse_controlled_link(
    *,
    preview: ControlledPilotPreview,
    settings: ConnectorSettings,
    expected_member_id: str,
    update: Callable[[OpenLineUpdatePreview], Awaitable[bool]],
    read_snapshot: Callable[[], Awaitable[OpenLineConfigSnapshot]],
    receipt_waiter: Callable[[], Awaitable[ControlledR0Receipt]],
    receipt_timeout_seconds: float,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> LinkRehearsalResult:
    if (
        receipt_timeout_seconds <= 0
        or receipt_timeout_seconds > MAX_R0_RECEIPT_WAIT_SECONDS
    ):
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.BLOCKED,
            reason="link_rehearsal_receipt_timeout_invalid",
        )
    error = _validate_contract(
        preview=preview,
        settings=settings,
        expected_member_id=expected_member_id,
        now=clock(),
    )
    if error:
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.BLOCKED,
            reason=error,
        )

    try:
        original = await read_snapshot()
    except Exception:
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.BLOCKED,
            reason="link_rehearsal_snapshot_unavailable",
        )
    if (
        not _snapshot_is_original(original)
        or _welcome_values(original) != _preview_values(preview.rollback)
    ):
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.BLOCKED,
            reason="link_rehearsal_snapshot_not_original",
        )

    link_attempts = 0
    rollback_attempts = 0
    link_verified = False
    off_verified = False
    receipt_verified = False
    operation_error: Optional[str] = None
    rollback_error: Optional[str] = None
    rollback_verified = False
    try:
        link_attempts = 1
        if not await update(preview.link):
            operation_error = "link_rehearsal_link_rejected"
        else:
            linked = await read_snapshot()
            link_verified = (
                linked.config_id == CONTROLLED_CONFIG_ID
                and _welcome_values(linked) == _preview_values(preview.link)
            )
            if not link_verified:
                operation_error = "link_rehearsal_link_not_verified"
            else:
                try:
                    receipt = await asyncio.wait_for(
                        receipt_waiter(),
                        timeout=receipt_timeout_seconds,
                    )
                except TimeoutError:
                    operation_error = "link_rehearsal_receipt_timeout"
                else:
                    receipt_verified = receipt_is_exact(
                        receipt,
                        preview.allowlist,
                    )
                    off_verified = receipt_verified
                    if not receipt_verified:
                        operation_error = "link_rehearsal_receipt_mismatch"
    except Exception:
        operation_error = "link_rehearsal_operation_failed"
    finally:
        rollback_attempts = 1
        try:
            if not await update(preview.rollback):
                rollback_error = "link_rehearsal_rollback_rejected"
            else:
                restored = await read_snapshot()
                rollback_verified = (
                    _snapshot_is_original(restored)
                    and _welcome_values(restored)
                    == _preview_values(preview.rollback)
                )
                if not rollback_verified:
                    rollback_error = "link_rehearsal_rollback_not_verified"
        except Exception:
            rollback_error = "link_rehearsal_rollback_failed"

    if rollback_error:
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.ROLLBACK_FAILED,
            reason=rollback_error,
            link_attempts=link_attempts,
            rollback_attempts=rollback_attempts,
            link_verified=link_verified,
            off_verified=off_verified,
            receipt_verified=receipt_verified,
        )
    if operation_error:
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.FAILED_RESTORED,
            reason=operation_error,
            link_attempts=link_attempts,
            rollback_attempts=rollback_attempts,
            link_verified=link_verified,
            off_verified=off_verified,
            receipt_verified=receipt_verified,
            rollback_verified=True,
        )
    return LinkRehearsalResult(
        status=LinkRehearsalStatus.RESTORED,
        reason="link_rehearsal_completed_and_restored",
        link_attempts=1,
        rollback_attempts=1,
        link_verified=True,
        off_verified=True,
        receipt_verified=True,
        rollback_verified=True,
    )
