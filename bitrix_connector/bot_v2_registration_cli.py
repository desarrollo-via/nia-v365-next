"""Ejecucion A4 acotada: preflight, alta unica y verificacion por lectura."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .bot_v2_preflight import (
    CONTROLLED_BOT_CODE,
    BitrixBotV2PreflightClient,
    BotV2PreflightInspector,
    BotV2PreflightResult,
    BotV2PreflightStatus,
    build_controlled_registration_preview,
)
from .bot_v2_preflight_cli import _load_local_settings
from .bot_v2_registration import (
    BitrixBotV2RegistrationClient,
    ControlledBotRegistrationRunner,
    ControlledRegistrationResult,
    ControlledRegistrationStatus,
)
from .config import ConnectorSettings
from .openline_pilot_preflight import (
    BitrixOpenLinePreflightClient,
    OpenLinePreflightInspector,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
)
from .pilot_discovery_factory import (
    PilotDiscoveryOAuthFactory,
    PilotDiscoveryOAuthResources,
)


STABLE_WEBHOOK_URL = (
    "https://nia-v365-next-api-ekd4fza7e0fzevfd."
    "canadacentral-01.azurewebsites.net/bitrix-connector/webhook"
)
CONTROLLED_CHAT_ID = 78733
CONTROLLED_DIALOG_ID = "chat78733"
CONTROLLED_CONFIG_ID = 13
ORIGINAL_WELCOME_BOT_ID = 245339


class A4Status(str, Enum):
    REGISTERED = "registered"
    IDEMPOTENT = "idempotent"
    RETRY = "retry"
    FAILED = "failed"


class A4ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: A4Status
    reason: str
    rest_revision: Optional[int] = Field(default=None, ge=0)
    bot_id: Optional[int] = Field(default=None, gt=0)
    registration_attempted: bool = False
    registration_verified: bool = False
    line_config_id: Optional[int] = Field(default=None, gt=0)
    line_unchanged: bool = False
    effective_mode: str = "off"
    activation_locked: bool = True
    external_calls_enabled: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Registra una sola vez el bot controlado y verifica que la linea "
            "13 permanezca intacta."
        )
    )
    parser.add_argument(
        "--confirm-code",
        required=True,
        choices=[CONTROLLED_BOT_CODE],
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser


async def execute_bot_preflight_once(
    *,
    portal_url: str,
    access_token: str,
    timeout_seconds: float,
) -> BotV2PreflightResult:
    client = BitrixBotV2PreflightClient(
        portal_url=portal_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    try:
        return await BotV2PreflightInspector(client).inspect()
    finally:
        await client.close()


async def execute_line_preflight_once(
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


async def execute_registration_once(
    *,
    portal_url: str,
    access_token: str,
    timeout_seconds: float,
    preflight: BotV2PreflightResult,
) -> ControlledRegistrationResult:
    client = BitrixBotV2RegistrationClient(
        portal_url=portal_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    try:
        return await ControlledBotRegistrationRunner(client).run(
            preflight=preflight,
            preview=build_controlled_registration_preview(
                STABLE_WEBHOOK_URL
            ),
        )
    finally:
        await client.close()


def _line_is_original(result: OpenLinePreflightResult) -> bool:
    config = result.config
    return bool(
        result.status is OpenLinePreflightStatus.READY
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


def _failed(
    reason: str,
    *,
    bot: Optional[BotV2PreflightResult] = None,
    registration_attempted: bool = False,
    bot_id: Optional[int] = None,
) -> A4ExecutionResult:
    return A4ExecutionResult(
        status=A4Status.FAILED,
        reason=reason,
        rest_revision=bot.rest_revision if bot else None,
        bot_id=bot_id,
        registration_attempted=registration_attempted,
    )


async def execute_stored_oauth_registration(
    *,
    timeout_seconds: float = 10.0,
    settings: Optional[ConnectorSettings] = None,
    resources_factory: Optional[PilotDiscoveryOAuthFactory] = None,
    bot_preflight_once: Callable[..., object] = execute_bot_preflight_once,
    line_preflight_once: Callable[..., object] = execute_line_preflight_once,
    registration_once: Callable[..., object] = execute_registration_once,
) -> A4ExecutionResult:
    current_settings = settings or _load_local_settings()
    if (
        current_settings.effective_mode.value != "off"
        or not current_settings.activation_locked
        or current_settings.external_calls_enabled
    ):
        return _failed("a4_safety_barriers_invalid")

    resources: Optional[PilotDiscoveryOAuthResources] = None
    try:
        resources = await (
            resources_factory or PilotDiscoveryOAuthFactory()
        ).build(current_settings, timeout_seconds=timeout_seconds)
        token = await resources.oauth_provider.get_access_token(
            resources.member_id
        )
        before = await bot_preflight_once(
            portal_url=resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
        )
        if (
            before.status is BotV2PreflightStatus.RETRY
            and before.reason == "bot_v2_preflight_token_expired"
        ):
            token = await resources.oauth_provider.refresh_access_token(
                resources.member_id,
                token,
            )
            before = await bot_preflight_once(
                portal_url=resources.portal_url,
                access_token=token,
                timeout_seconds=timeout_seconds,
            )
        if before.status not in {
            BotV2PreflightStatus.READY,
            BotV2PreflightStatus.EXISTING_COMPATIBLE,
        }:
            return _failed("a4_bot_preflight_not_ready", bot=before)

        line_before = await line_preflight_once(
            portal_url=resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
        )
        if not _line_is_original(line_before):
            return _failed("a4_line_snapshot_not_original", bot=before)

        registration = await registration_once(
            portal_url=resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
            preflight=before,
        )
        if registration.status is ControlledRegistrationStatus.RETRY:
            return A4ExecutionResult(
                status=A4Status.RETRY,
                reason=registration.reason,
                rest_revision=before.rest_revision,
                registration_attempted=registration.registration_attempted,
                line_config_id=CONTROLLED_CONFIG_ID,
                line_unchanged=True,
            )
        if registration.status not in {
            ControlledRegistrationStatus.REGISTERED,
            ControlledRegistrationStatus.IDEMPOTENT,
        } or registration.bot_id is None:
            return _failed(
                registration.reason,
                bot=before,
                registration_attempted=registration.registration_attempted,
            )

        after = await bot_preflight_once(
            portal_url=resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
        )
        line_after = await line_preflight_once(
            portal_url=resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
        )
        bot_verified = (
            after.status is BotV2PreflightStatus.EXISTING_COMPATIBLE
            and after.existing_bot_id == registration.bot_id
        )
        line_unchanged = _line_is_original(line_after)
        if not bot_verified or not line_unchanged:
            return A4ExecutionResult(
                status=A4Status.FAILED,
                reason="a4_post_registration_verification_failed",
                rest_revision=after.rest_revision,
                bot_id=registration.bot_id,
                registration_attempted=registration.registration_attempted,
                registration_verified=bot_verified,
                line_config_id=CONTROLLED_CONFIG_ID,
                line_unchanged=line_unchanged,
            )
        return A4ExecutionResult(
            status=(
                A4Status.REGISTERED
                if registration.status is ControlledRegistrationStatus.REGISTERED
                else A4Status.IDEMPOTENT
            ),
            reason="a4_registration_verified_unlinked",
            rest_revision=after.rest_revision,
            bot_id=registration.bot_id,
            registration_attempted=registration.registration_attempted,
            registration_verified=True,
            line_config_id=CONTROLLED_CONFIG_ID,
            line_unchanged=True,
        )
    except Exception:
        return _failed("a4_registration_unavailable")
    finally:
        if resources is not None:
            await resources.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(
        execute_stored_oauth_registration(
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status in {A4Status.REGISTERED, A4Status.IDEMPOTENT} else 1


if __name__ == "__main__":
    raise SystemExit(main())
