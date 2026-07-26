"""Runner efímero del preflight v2 con OAuth almacenado y salida segura."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

from .bot_v2_preflight import (
    BitrixBotV2PreflightClient,
    BotV2PreflightInspector,
    BotV2PreflightResult,
    BotV2PreflightStatus,
)
from .config import ConnectorSettings, load_settings
from .pilot_discovery_factory import (
    PilotDiscoveryOAuthFactory,
    PilotDiscoveryOAuthResources,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Consulta únicamente imbot.v2.Revision.get y Bot.list "
            "con el OAuth almacenado."
        )
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser


def _load_local_settings() -> ConnectorSettings:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    return load_settings(values)


async def execute_preflight_once(
    *,
    portal_url: str,
    access_token: str,
    timeout_seconds: float,
    client_factory: Callable[..., BitrixBotV2PreflightClient] = (
        BitrixBotV2PreflightClient
    ),
) -> BotV2PreflightResult:
    client = client_factory(
        portal_url=portal_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    try:
        return await BotV2PreflightInspector(client).inspect()
    finally:
        await client.close()


async def execute_stored_oauth_preflight(
    *,
    timeout_seconds: float = 10.0,
    settings: Optional[ConnectorSettings] = None,
    resources_factory: Optional[PilotDiscoveryOAuthFactory] = None,
    execute_once: Callable[..., object] = execute_preflight_once,
) -> BotV2PreflightResult:
    resources: Optional[PilotDiscoveryOAuthResources] = None
    try:
        resources = await (
            resources_factory or PilotDiscoveryOAuthFactory()
        ).build(
            settings or _load_local_settings(),
            timeout_seconds=timeout_seconds,
        )
        token = await resources.oauth_provider.get_access_token(
            resources.member_id
        )
        result = await execute_once(
            portal_url=resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
        )
        if (
            result.status is BotV2PreflightStatus.RETRY
            and result.reason == "bot_v2_preflight_token_expired"
        ):
            token = await resources.oauth_provider.refresh_access_token(
                resources.member_id,
                token,
            )
            result = await execute_once(
                portal_url=resources.portal_url,
                access_token=token,
                timeout_seconds=timeout_seconds,
            )
        return result
    finally:
        if resources is not None:
            await resources.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(
            execute_stored_oauth_preflight(
                timeout_seconds=args.timeout_seconds,
            )
        )
    except Exception:
        result = BotV2PreflightResult(
            status=BotV2PreflightStatus.FAILED,
            reason="bot_v2_preflight_unavailable",
        )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status in {
        BotV2PreflightStatus.READY,
        BotV2PreflightStatus.EXISTING_COMPATIBLE,
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
