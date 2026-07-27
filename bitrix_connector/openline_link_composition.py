"""Composicion hermetica de dos mutaciones one-shot con OAuth inyectado."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol

from .bitrix_client import BitrixAccessTokenProvider
from .config import ConnectorSettings
from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    ORIGINAL_WELCOME_BOT_ID,
    LinkRehearsalResult,
    LinkRehearsalStatus,
    rehearse_controlled_link,
)
from .openline_pilot_preflight import (
    BitrixOpenLinePreflightClient,
    ControlledPilotPreview,
    OpenLineConfigSnapshot,
    OpenLineReadDecision,
    OpenLineUpdatePreview,
)
from .openline_update_adapter import (
    BitrixOpenLineUpdateClient,
    OneShotVerifiedOpenLineUpdate,
    VerifiedUpdateStatus,
)
from .openline_r0_receipt import ControlledR0Receipt


class InjectedOpenLineOAuthResources(Protocol):
    oauth_provider: BitrixAccessTokenProvider
    portal_url: str
    member_id: str

    async def close(self) -> None: ...


@dataclass
class OpenLineLinkHttpResources:
    """Posee dos pares independientes update/read y los cierra en reversa."""

    link_update_client: BitrixOpenLineUpdateClient
    link_read_client: BitrixOpenLinePreflightClient
    rollback_update_client: BitrixOpenLineUpdateClient
    rollback_read_client: BitrixOpenLinePreflightClient
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def build(
        cls,
        *,
        portal_url: str,
        access_token: str,
        timeout_seconds: float,
    ) -> "OpenLineLinkHttpResources":
        return cls(
            link_update_client=BitrixOpenLineUpdateClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            ),
            link_read_client=BitrixOpenLinePreflightClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            ),
            rollback_update_client=BitrixOpenLineUpdateClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            ),
            rollback_read_client=BitrixOpenLinePreflightClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            ),
        )

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        first_error: Optional[BaseException] = None
        for client in (
            self.rollback_read_client,
            self.rollback_update_client,
            self.link_read_client,
            self.link_update_client,
        ):
            try:
                await client.close()
            except BaseException as exc:  # pragma: no cover - cierre defensivo
                first_error = first_error or exc
        if first_error is not None:
            raise first_error


HttpResourcesFactory = Callable[..., OpenLineLinkHttpResources]


async def rehearse_controlled_link_with_injected_oauth(
    *,
    preview: ControlledPilotPreview,
    settings: ConnectorSettings,
    oauth_resources: InjectedOpenLineOAuthResources,
    receipt_waiter: Callable[[], Awaitable[ControlledR0Receipt]],
    receipt_timeout_seconds: float,
    timeout_seconds: float,
    http_resources_factory: HttpResourcesFactory = OpenLineLinkHttpResources.build,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> LinkRehearsalResult:
    """Ejecuta el coordinador sin leer entorno, renovar token o reintentar."""

    if timeout_seconds <= 0:
        return LinkRehearsalResult(
            status=LinkRehearsalStatus.BLOCKED,
            reason="link_rehearsal_timeout_invalid",
        )

    http_resources: Optional[OpenLineLinkHttpResources] = None
    phase = "before_link"

    async def ensure_http_resources() -> OpenLineLinkHttpResources:
        nonlocal http_resources
        if http_resources is None:
            token = await oauth_resources.oauth_provider.get_access_token(
                oauth_resources.member_id
            )
            http_resources = http_resources_factory(
                portal_url=oauth_resources.portal_url,
                access_token=token,
                timeout_seconds=timeout_seconds,
            )
        return http_resources

    async def read_snapshot() -> OpenLineConfigSnapshot:
        resources = await ensure_http_resources()
        reader = (
            resources.rollback_read_client
            if phase == "rollback"
            else resources.link_read_client
        )
        read = await reader.get_config(preview.rollback.payload.CONFIG_ID)
        if read.decision is not OpenLineReadDecision.SUCCESS or read.config is None:
            raise RuntimeError("link_rehearsal_snapshot_unavailable")
        return read.config

    async def update(contract: OpenLineUpdatePreview) -> bool:
        nonlocal phase
        resources = await ensure_http_resources()
        bot_id = contract.payload.PARAMS.WELCOME_BOT_ID
        if bot_id == CONTROLLED_BOT_ID and phase == "before_link":
            phase = "link"
            adapter = OneShotVerifiedOpenLineUpdate(
                resources.link_update_client,
                resources.link_read_client,
            )
        elif bot_id == ORIGINAL_WELCOME_BOT_ID and phase in {"link", "before_link"}:
            phase = "rollback"
            adapter = OneShotVerifiedOpenLineUpdate(
                resources.rollback_update_client,
                resources.rollback_read_client,
            )
        else:
            return False
        result = await adapter.apply(contract)
        return result.status is VerifiedUpdateStatus.VERIFIED

    result: Optional[LinkRehearsalResult] = None
    close_failed = False
    try:
        result = await rehearse_controlled_link(
            preview=preview,
            settings=settings,
            expected_member_id=oauth_resources.member_id,
            update=update,
            read_snapshot=read_snapshot,
            receipt_waiter=receipt_waiter,
            receipt_timeout_seconds=receipt_timeout_seconds,
            clock=clock,
        )
    except Exception:
        result = LinkRehearsalResult(
            status=LinkRehearsalStatus.BLOCKED,
            reason="link_rehearsal_composition_failed_safe",
        )
    finally:
        if http_resources is not None:
            try:
                await http_resources.close()
            except BaseException:
                close_failed = True
        try:
            await oauth_resources.close()
        except BaseException:
            close_failed = True

    if close_failed and result.status is not LinkRehearsalStatus.ROLLBACK_FAILED:
        return LinkRehearsalResult(
            status=(
                LinkRehearsalStatus.FAILED_RESTORED
                if result.rollback_verified
                else LinkRehearsalStatus.BLOCKED
            ),
            reason="link_rehearsal_resource_close_failed",
            link_attempts=result.link_attempts,
            rollback_attempts=result.rollback_attempts,
            link_verified=result.link_verified,
            off_verified=result.off_verified,
            receipt_verified=result.receipt_verified,
            rollback_verified=result.rollback_verified,
        )
    return result
