"""Dormant, exact HTTP transport for the protected R1 host probe."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .r1_key_vault_protected_probe_invocation_owner import (
    PROBE_ENDPOINT,
    REQUEST_TIMEOUT_SECONDS,
    ProtectedProbeHttpResponse,
)


MAX_RESPONSE_BYTES = 4096


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("r1_probe_http_duplicate_json_key")
        result[key] = value
    return result


def _decode_payload(raw: bytes) -> Any:
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        return None
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object_without_duplicates
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None


class ProtectedProbeTransportFailure(RuntimeError):
    """Sanitized terminal transport failure after a possible one-shot send."""

    def __init__(self) -> None:
        super().__init__("r1_probe_transport_ambiguous")


class ExactOneShotProtectedProbeHttpTransport:
    """One GET, no redirects/retries, bounded body and no secret output."""

    kind = "production-http"
    __slots__ = ("_client", "_closed", "_owns_client", "_used")

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        owns_client: bool = False,
    ) -> None:
        if type(client) is not httpx.AsyncClient:
            raise TypeError("r1_probe_http_client_invalid")
        self._client: httpx.AsyncClient | None = client
        self._owns_client = owns_client
        self._used = False
        self._closed = False

    def __repr__(self) -> str:
        return "ExactOneShotProtectedProbeHttpTransport(<redacted>)"

    async def get_exact_once(
        self,
        *,
        url: str,
        bearer_token: bytearray,
        timeout_seconds: int,
        follow_redirects: bool,
    ) -> ProtectedProbeHttpResponse:
        if (
            self._used
            or self._closed
            or self._client is None
            or url != PROBE_ENDPOINT
            or timeout_seconds != REQUEST_TIMEOUT_SECONDS
            or follow_redirects is not False
            or type(bearer_token) is not bytearray
            or not 24 <= len(bearer_token) <= 4096
            or b"\x00" in bearer_token
        ):
            self._used = True
            raise RuntimeError("r1_probe_http_request_contract_invalid")
        self._used = True
        try:
            token_text = bytes(bearer_token).decode("utf-8")
        except UnicodeDecodeError:
            raise RuntimeError("r1_probe_http_token_encoding_invalid") from None
        authorization = f"Bearer {token_text}"
        token_text = ""
        body = bytearray()
        try:
            async with self._client.stream(
                "GET",
                PROBE_ENDPOINT,
                headers={"Authorization": authorization, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as response:
                status_code = response.status_code
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        body.clear()
                        return ProtectedProbeHttpResponse(status_code, None)
                    body.extend(chunk)
        except httpx.HTTPError:
            raise ProtectedProbeTransportFailure() from None
        finally:
            authorization = ""
        payload = _decode_payload(bytes(body))
        body.clear()
        return ProtectedProbeHttpResponse(status_code, payload)

    async def close(self) -> None:
        client, self._client = self._client, None
        if self._closed:
            return
        self._closed = True
        if self._owns_client and client is not None:
            await client.aclose()


def build_dormant_production_http_transport(
) -> ExactOneShotProtectedProbeHttpTransport:
    """Builds an inert client; construction performs no request."""

    client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
    )
    return ExactOneShotProtectedProbeHttpTransport(
        client=client,
        owns_client=True,
    )


__all__ = [
    "ExactOneShotProtectedProbeHttpTransport",
    "MAX_RESPONSE_BYTES",
    "ProtectedProbeTransportFailure",
    "build_dormant_production_http_transport",
]
