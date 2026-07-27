"""Cliente inyectable del puente R0; la CLI lo compone solo por opt-in."""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from collections.abc import Callable
from typing import Optional

import httpx
from pydantic import SecretStr

from .openline_link_rehearsal import (
    CONTROLLED_BOT_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DIALOG_ID,
)
from .openline_r0_bridge import (
    R0BridgeArmRequest,
    R0BridgeCode,
    R0BridgeResponse,
    R0_BRIDGE_PREFIX,
    RUN_ID_PATTERN,
)
from .openline_r0_receipt import (
    ControlledR0Receipt,
    MAX_R0_RECEIPT_WAIT_SECONDS,
)
from .pilot_scope import PilotScopeRule
from .review_auth import MIN_REVIEW_TOKEN_CHARS


def _bridge_root(public_origin: str) -> str:
    parsed = httpx.URL(public_origin.strip().rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.host
        or parsed.userinfo
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.port not in {None, 443}
    ):
        raise ValueError("r0_bridge_origin_invalid")
    return f"{str(parsed).rstrip('/')}{R0_BRIDGE_PREFIX}"


class HttpR0ReceiptGate:
    """Arma, consulta y consume una sesion remota de un solo uso."""

    def __init__(
        self,
        *,
        public_origin: str,
        review_token: str,
        poll_interval_seconds: float = 0.5,
        http_client: Optional[httpx.AsyncClient] = None,
        run_id_factory: Callable[[], str] = lambda: secrets.token_hex(32),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        token = review_token.strip()
        if len(token) < MIN_REVIEW_TOKEN_CHARS:
            raise ValueError("r0_bridge_review_token_invalid")
        if not 0 < poll_interval_seconds <= 5:
            raise ValueError("r0_bridge_poll_interval_invalid")
        self._root = _bridge_root(public_origin)
        self._token = SecretStr(token)
        self._poll_interval_seconds = poll_interval_seconds
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=10.0)
        self._run_id_factory = run_id_factory
        self._monotonic = monotonic
        self._run_id: Optional[SecretStr] = None
        self._closed = False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": (
                f"Bearer {self._token.get_secret_value()}"
            ),
            "Cache-Control": "no-store",
        }

    def _run_id_value(self) -> str:
        if self._run_id is None:
            raise RuntimeError("r0_bridge_not_armed")
        return self._run_id.get_secret_value()

    async def arm(self, rule: PilotScopeRule) -> None:
        if self._closed or self._run_id is not None:
            raise RuntimeError("r0_bridge_not_armable")
        if (
            rule.bot_id != CONTROLLED_BOT_ID
            or rule.chat_id != CONTROLLED_CHAT_ID
            or rule.dialog_id != CONTROLLED_DIALOG_ID
            or rule.valid_from is None
            or rule.valid_until is None
        ):
            raise RuntimeError("r0_bridge_scope_invalid")
        run_id = self._run_id_factory()
        if re.fullmatch(RUN_ID_PATTERN, run_id) is None:
            raise RuntimeError("r0_bridge_run_id_invalid")
        payload = R0BridgeArmRequest(
            run_id=run_id,
            member_id=rule.member_id,
            bot_id=rule.bot_id,
            chat_id=rule.chat_id,
            dialog_id=rule.dialog_id,
            valid_from=rule.valid_from,
            valid_until=rule.valid_until,
        )
        response = await self._http.post(
            f"{self._root}/arm",
            headers=self._headers(),
            json=payload.model_dump(mode="json"),
        )
        if response.status_code != 201:
            raise RuntimeError("r0_bridge_arm_failed")
        parsed = R0BridgeResponse.model_validate(response.json())
        if parsed.code is not R0BridgeCode.ARMED:
            raise RuntimeError("r0_bridge_arm_failed")
        self._run_id = SecretStr(run_id)

    async def wait(self) -> ControlledR0Receipt:
        run_id = self._run_id_value()
        deadline = self._monotonic() + MAX_R0_RECEIPT_WAIT_SECONDS
        while self._monotonic() < deadline:
            response = await self._http.get(
                f"{self._root}/{run_id}",
                headers=self._headers(),
            )
            if response.status_code != 200:
                raise RuntimeError("r0_bridge_inspect_failed")
            state = R0BridgeResponse.model_validate(response.json())
            if state.code is R0BridgeCode.PENDING:
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            if state.code is not R0BridgeCode.AVAILABLE:
                raise RuntimeError("r0_bridge_inspect_failed")
            consumed_response = await self._http.post(
                f"{self._root}/{run_id}/consume",
                headers=self._headers(),
            )
            if consumed_response.status_code != 200:
                raise RuntimeError("r0_bridge_consume_failed")
            consumed = R0BridgeResponse.model_validate(
                consumed_response.json()
            )
            if (
                consumed.code is not R0BridgeCode.CONSUMED
                or consumed.receipt is None
            ):
                raise RuntimeError("r0_bridge_consume_failed")
            self._run_id = None
            return consumed.receipt
        raise TimeoutError("r0_bridge_wait_timeout")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._run_id is not None:
            run_id = self._run_id.get_secret_value()
            try:
                await self._http.delete(
                    f"{self._root}/{run_id}",
                    headers=self._headers(),
                )
            except Exception:
                pass
            self._run_id = None
        if self._owns_http:
            await self._http.aclose()


__all__ = ["HttpR0ReceiptGate"]
