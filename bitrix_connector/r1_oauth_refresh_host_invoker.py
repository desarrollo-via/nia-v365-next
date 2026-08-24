"""Invocador one-shot del endpoint OAuth R1, construido sólo por inyección."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from .r1_oauth_refresh_internal_endpoint import R1_OAUTH_REFRESH_INTERNAL_PATH


@dataclass(frozen=True)
class R1OAuthRefreshHostInvocationSnapshot:
    state: Literal["READY", "NO-GO"]
    reason: str
    token_requests: int = 0
    endpoint_requests: int = 0


TokenProvider = Callable[[], Awaitable[str]]
EndpointCaller = Callable[[str, str], Awaitable[int]]


async def invoke_r1_oauth_refresh_from_host_once(
    *,
    token_provider: TokenProvider,
    endpoint_caller: EndpointCaller,
) -> R1OAuthRefreshHostInvocationSnapshot:
    """Pide un JWT y llama una sola vez; no imprime ni devuelve el token."""

    if not callable(token_provider) or not callable(endpoint_caller):
        return R1OAuthRefreshHostInvocationSnapshot("NO-GO", "dependencies_invalid")
    try:
        token = await token_provider()
        if type(token) is not str or not token.strip():
            return R1OAuthRefreshHostInvocationSnapshot("NO-GO", "identity_token_rejected", 1)
        status = await endpoint_caller(R1_OAUTH_REFRESH_INTERNAL_PATH, token)
    except BaseException:
        return R1OAuthRefreshHostInvocationSnapshot("NO-GO", "host_invocation_failed", 1)
    if status != 200:
        return R1OAuthRefreshHostInvocationSnapshot("NO-GO", "endpoint_rejected", 1, 1)
    return R1OAuthRefreshHostInvocationSnapshot("READY", "endpoint_invoked", 1, 1)


__all__ = ["R1OAuthRefreshHostInvocationSnapshot", "invoke_r1_oauth_refresh_from_host_once"]
