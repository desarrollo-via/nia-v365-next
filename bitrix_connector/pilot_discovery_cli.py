"""Comando local y explícito para una consulta piloto de solo lectura."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

from .config import ConnectorSettings, load_settings

from .pilot_discovery import (
    BitrixPilotDiscoveryClient,
    PilotChatInspector,
    PilotDiscoveryRequest,
    PilotDiscoveryStatus,
)
from .pilot_discovery_factory import (
    PilotDiscoveryOAuthFactory,
    PilotDiscoveryOAuthResources,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Consulta los chats de una negociación mediante "
            "imopenlines.crm.chat.get; no modifica Bitrix."
        )
    )
    parser.add_argument("--deal-id", required=True, type=int)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser


async def execute_read_only_discovery(
    *,
    portal_url: str,
    deal_id: int,
    access_token: str,
    member_id: Optional[str] = None,
    bot_id: Optional[int] = None,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    request = PilotDiscoveryRequest(
        crm_entity_type="deal",
        crm_entity_id=deal_id,
        member_id=member_id,
        bot_id=bot_id,
        active_only=False,
    )
    async with BitrixPilotDiscoveryClient(
        portal_url=portal_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    ) as client:
        result = await PilotChatInspector(client).inspect(request)
    return result.model_dump(mode="json")


def _load_local_settings() -> ConnectorSettings:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    return load_settings(values)


async def execute_stored_oauth_discovery(
    *,
    deal_id: int,
    timeout_seconds: float = 10.0,
    settings: Optional[ConnectorSettings] = None,
    factory: Optional[PilotDiscoveryOAuthFactory] = None,
) -> dict[str, object]:
    resources: Optional[PilotDiscoveryOAuthResources] = None
    try:
        resources = await (factory or PilotDiscoveryOAuthFactory()).build(
            settings or _load_local_settings(),
            timeout_seconds=timeout_seconds,
        )
        access_token = await resources.oauth_provider.get_access_token(
            resources.member_id
        )
        result = await execute_read_only_discovery(
            portal_url=resources.portal_url,
            deal_id=deal_id,
            access_token=access_token,
            timeout_seconds=timeout_seconds,
        )
        if (
            result.get("status") == PilotDiscoveryStatus.RETRY.value
            and result.get("reason") == "pilot_discovery_token_expired"
        ):
            access_token = await resources.oauth_provider.refresh_access_token(
                resources.member_id,
                access_token,
            )
            result = await execute_read_only_discovery(
                portal_url=resources.portal_url,
                deal_id=deal_id,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            )
        return result
    finally:
        if resources is not None:
            await resources.close()


def main(
    argv: Optional[Sequence[str]] = None,
) -> int:
    args = build_parser().parse_args(argv)
    output = asyncio.run(
        execute_stored_oauth_discovery(
            deal_id=args.deal_id,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] in {
        PilotDiscoveryStatus.FOUND.value,
        PilotDiscoveryStatus.EMPTY.value,
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
