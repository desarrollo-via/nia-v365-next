"""Authenticated, one-shot HTTP client for the remotely mounted R1 owner."""

from __future__ import annotations

from typing import Optional

import httpx
from pydantic import SecretStr, ValidationError

from .bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from .review_auth import MIN_REVIEW_TOKEN_CHARS


def _root(public_origin: str) -> str:
    parsed = httpx.URL(public_origin.strip().rstrip("/"))
    if (
        parsed.scheme != "https" or not parsed.host or parsed.userinfo
        or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
        or parsed.port not in {None, 443}
    ):
        raise ValueError("r1_remote_control_origin_invalid")
    return f"{str(parsed).rstrip('/')}/bitrix-connector/internal/r1-event"


class ExactR1RemoteSessionHttpClient:
    """Calls only the four frozen control routes; never logs payloads."""

    __slots__ = ("_closed", "_http", "_owns_http", "_root", "_token")

    def __init__(
        self, *, public_origin: str, review_token: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        token = review_token.strip()
        if len(token) < MIN_REVIEW_TOKEN_CHARS:
            raise ValueError("r1_remote_control_token_invalid")
        self._root = _root(public_origin)
        self._token = SecretStr(token)
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=10.0)
        self._closed = False

    def _headers(self) -> dict[str, str]:
        if self._closed:
            raise RuntimeError("r1_remote_control_client_closed")
        return {
            "Authorization": f"Bearer {self._token.get_secret_value()}",
            "Cache-Control": "no-store",
        }

    async def _request(self, method: str, suffix: str, *, confirmation=None):
        response = await self._http.request(
            method, f"{self._root}{suffix}", headers=self._headers(),
            json={"confirmation": confirmation} if confirmation is not None else None,
        )
        if response.status_code != 200:
            raise RuntimeError("r1_remote_control_request_failed")
        try:
            return EventR1ControlSnapshot.model_validate(response.json())
        except (TypeError, ValueError, ValidationError):
            raise RuntimeError("r1_remote_control_response_invalid") from None

    async def first_confirmation_once(self, confirmation: str):
        return await self._request(
            "POST", "/first-confirmation", confirmation=confirmation
        )

    async def second_confirmation_once(self, confirmation: str):
        return await self._request(
            "POST", "/second-confirmation", confirmation=confirmation
        )

    async def status_once(self):
        return await self._request("GET", "/status")

    async def disarm_once(self):
        return await self._request("DELETE", "/session")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._token = SecretStr("")
        if self._owns_http:
            await self._http.aclose()

    def __repr__(self) -> str:
        return "ExactR1RemoteSessionHttpClient(<redacted>)"


__all__ = ["ExactR1RemoteSessionHttpClient"]
