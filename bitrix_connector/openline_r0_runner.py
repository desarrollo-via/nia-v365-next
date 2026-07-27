"""Runner one-shot fail-closed para el futuro ensayo R0 controlado."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .config import ConnectorSettings
from .openline_link_composition import (
    HttpResourcesFactory,
    OpenLineLinkHttpResources,
    rehearse_controlled_link_with_injected_oauth,
)
from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_CONFIG_ID,
    CONTROLLED_DIALOG_ID,
    ORIGINAL_WELCOME_BOT_ID,
    LinkRehearsalResult,
    LinkRehearsalStatus,
)
from .openline_pilot_preflight import (
    BitrixOpenLinePreflightClient,
    OpenLinePreflightInspector,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
    build_controlled_pilot_preview,
)
from .openline_r0_receipt import (
    MAX_R0_RECEIPT_WAIT_SECONDS,
    R0ReceiptGate,
)
from .pilot_discovery_factory import (
    PilotDiscoveryOAuthFactory,
    PilotDiscoveryOAuthResources,
)


CONTROLLED_R0_CONFIRMATION = (
    "VINCULAR 373259 LINEA 13 CHAT78733 Y RESTAURAR 245339"
)
CONTROLLED_R0_WINDOW = timedelta(minutes=10)
CONTROLLED_R0_RECEIPT_WAIT_SECONDS = 180.0
STABLE_WEBHOOK_URL = (
    "https://nia-v365-next-api-ekd4fza7e0fzevfd."
    "canadacentral-01.azurewebsites.net/bitrix-connector/webhook"
)


class ControlledR0RunnerStatus(str, Enum):
    RESTORED = "restored"
    BLOCKED = "blocked"
    FAILED_RESTORED = "failed_restored"
    ROLLBACK_FAILED = "rollback_failed"


class ControlledR0RunnerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ControlledR0RunnerStatus
    reason: str
    preflight_completed: bool = False
    delegated: bool = False
    link_attempts: int = 0
    rollback_attempts: int = 0
    link_verified: bool = False
    off_verified: bool = False
    receipt_verified: bool = False
    rollback_verified: bool = False


class _OneShotTokenProvider:
    def __init__(self, *, member_id: str, access_token: str) -> None:
        self._member_id = member_id
        self._access_token = access_token
        self._used = False

    async def get_access_token(self, member_id: str) -> str:
        if self._used or member_id != self._member_id:
            raise RuntimeError("r0_cached_token_unavailable")
        self._used = True
        return self._access_token

    async def refresh_access_token(
        self,
        member_id: str,
        stale_access_token: str,
    ) -> str:
        raise RuntimeError("r0_token_refresh_forbidden")


class _PreparedOAuthResources:
    def __init__(
        self,
        original: PilotDiscoveryOAuthResources,
        access_token: str,
    ) -> None:
        self.portal_url = original.portal_url
        self.member_id = original.member_id
        self.oauth_provider = _OneShotTokenProvider(
            member_id=original.member_id,
            access_token=access_token,
        )
        self._original = original
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._original.close()


async def execute_fresh_line_preflight_once(
    *,
    portal_url: str,
    access_token: str,
    timeout_seconds: float,
) -> OpenLinePreflightResult:
    client = BitrixOpenLinePreflightClient(
        portal_url=portal_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    try:
        return await OpenLinePreflightInspector(client).inspect(
            chat_id=CONTROLLED_CHAT_ID,
            dialog_id=CONTROLLED_DIALOG_ID,
        )
    finally:
        await client.close()


def _snapshot_is_exact(result: OpenLinePreflightResult) -> bool:
    config = result.config
    return bool(
        result.status is OpenLinePreflightStatus.READY
        and result.chat_id == CONTROLLED_CHAT_ID
        and result.dialog_id == CONTROLLED_DIALOG_ID
        and config is not None
        and config.config_id == CONTROLLED_CONFIG_ID
        and config.active == "Y"
        and config.welcome_bot_enable == "Y"
        and config.welcome_bot_join == "always"
        and config.welcome_bot_id == ORIGINAL_WELCOME_BOT_ID
        and config.welcome_bot_time == 0
        and config.welcome_bot_left == "close"
        and config.no_answer_bot_id == 0
        and config.close_bot_id == 0
        and config.auto_close_bot_id == 0
        and config.worktime_dayoff_bot_id == 0
    )


def _blocked(reason: str, *, preflight_completed: bool = False) -> ControlledR0RunnerResult:
    return ControlledR0RunnerResult(
        status=ControlledR0RunnerStatus.BLOCKED,
        reason=reason,
        preflight_completed=preflight_completed,
    )


def _from_rehearsal(result: LinkRehearsalResult) -> ControlledR0RunnerResult:
    status = {
        LinkRehearsalStatus.RESTORED: ControlledR0RunnerStatus.RESTORED,
        LinkRehearsalStatus.BLOCKED: ControlledR0RunnerStatus.BLOCKED,
        LinkRehearsalStatus.FAILED_RESTORED: (
            ControlledR0RunnerStatus.FAILED_RESTORED
        ),
        LinkRehearsalStatus.ROLLBACK_FAILED: (
            ControlledR0RunnerStatus.ROLLBACK_FAILED
        ),
    }[result.status]
    return ControlledR0RunnerResult(
        status=status,
        reason=result.reason,
        preflight_completed=True,
        delegated=True,
        link_attempts=result.link_attempts,
        rollback_attempts=result.rollback_attempts,
        link_verified=result.link_verified,
        off_verified=result.off_verified,
        receipt_verified=result.receipt_verified,
        rollback_verified=result.rollback_verified,
    )


async def execute_controlled_r0_runner(
    *,
    confirmation: str,
    settings: ConnectorSettings,
    receipt_gate: Optional[R0ReceiptGate] = None,
    receipt_timeout_seconds: float = CONTROLLED_R0_RECEIPT_WAIT_SECONDS,
    timeout_seconds: float = 10.0,
    resources_factory: Optional[PilotDiscoveryOAuthFactory] = None,
    preflight_once: Callable[..., Awaitable[OpenLinePreflightResult]] = (
        execute_fresh_line_preflight_once
    ),
    composition: Callable[..., Awaitable[LinkRehearsalResult]] = (
        rehearse_controlled_link_with_injected_oauth
    ),
    http_resources_factory: HttpResourcesFactory = OpenLineLinkHttpResources.build,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ControlledR0RunnerResult:
    """Carga OAuth almacenado solo tras confirmar; no lee entorno ni reintenta."""

    if confirmation != CONTROLLED_R0_CONFIRMATION:
        return _blocked("r0_confirmation_mismatch")
    if receipt_gate is None:
        return _blocked("r0_receipt_gate_required")
    if (
        receipt_timeout_seconds <= 0
        or receipt_timeout_seconds > MAX_R0_RECEIPT_WAIT_SECONDS
    ):
        return _blocked("r0_receipt_timeout_invalid")
    if timeout_seconds <= 0:
        return _blocked("r0_timeout_invalid")
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        return _blocked("r0_clock_not_aware")
    if (
        settings.effective_mode.value != "off"
        or not settings.activation_locked
        or settings.external_calls_enabled
    ):
        return _blocked("r0_safety_barriers_invalid")

    raw_resources: Optional[PilotDiscoveryOAuthResources] = None
    prepared: Optional[_PreparedOAuthResources] = None
    try:
        raw_resources = await (
            resources_factory or PilotDiscoveryOAuthFactory()
        ).build(settings, timeout_seconds=timeout_seconds)
        access_token = await raw_resources.oauth_provider.get_access_token(
            raw_resources.member_id
        )
        preflight = await preflight_once(
            portal_url=raw_resources.portal_url,
            access_token=access_token,
            timeout_seconds=timeout_seconds,
        )
        if not _snapshot_is_exact(preflight):
            return _blocked(
                "r0_fresh_preflight_not_exact",
                preflight_completed=True,
            )
        prepared = _PreparedOAuthResources(raw_resources, access_token)
        raw_resources = None
        preview = build_controlled_pilot_preview(
            preflight=preflight,
            bot_id=CONTROLLED_BOT_ID,
            member_id=prepared.member_id,
            webhook_url=STABLE_WEBHOOK_URL,
            valid_from=now,
            valid_until=now + CONTROLLED_R0_WINDOW,
        )
        await receipt_gate.arm(preview.allowlist)
        result = await composition(
            preview=preview,
            settings=settings,
            oauth_resources=prepared,
            receipt_waiter=receipt_gate.wait,
            receipt_timeout_seconds=receipt_timeout_seconds,
            timeout_seconds=timeout_seconds,
            http_resources_factory=http_resources_factory,
            clock=clock,
        )
        return _from_rehearsal(result)
    except Exception:
        return _blocked("r0_runner_failed_safe")
    finally:
        try:
            await receipt_gate.close()
        except BaseException:
            pass
        if prepared is not None:
            try:
                await prepared.close()
            except BaseException:
                pass
        elif raw_resources is not None:
            try:
                await raw_resources.close()
            except BaseException:
                pass
