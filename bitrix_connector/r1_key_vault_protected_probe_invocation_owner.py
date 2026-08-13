"""Fixture-only owner for the future protected host-probe invocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .r1_key_vault_protected_probe_invocation_policy import (
    ProtectedProbeInvocationState,
    evaluate_protected_probe_result,
)


FIXTURE_AUTHORIZATION = "VALIDATE PROTECTED R1 PROBE WITH INJECTED DOUBLES ONLY"
REVIEW_TOKEN_NAME = "NIA_BITRIX_REVIEW_TOKEN"
PROBE_ENDPOINT = (
    "https://nia-v365-next-api-ekd4fza7e0fzevfd.canadacentral-01."
    "azurewebsites.net/bitrix-connector/review/r1-key-vault-host-probe"
)
REQUEST_TIMEOUT_SECONDS = 15
HELPER_FAILED = "NO-GO-FIXTURE-HELPER-FAILED"
HELPER_REMAINDER = "NO-GO-REMAINDER"


@dataclass(frozen=True)
class ProtectedProbeHttpResponse:
    status_code: int
    payload: Any


FixtureProbeHttpResponse = ProtectedProbeHttpResponse


@dataclass(frozen=True)
class SanitizedFixtureInvocationResult:
    state: str
    credential_source_reads: int
    transport_calls: int
    retries: int
    redirects_followed: int
    real_network_calls: int
    secret_cleared: bool
    source_closed: bool
    transport_closed: bool


class FixtureProtectedTokenSource(Protocol):
    kind: str

    async def open(self) -> None: ...

    async def read_exact(self, name: str) -> bytearray: ...

    async def close(self) -> None: ...


class FixtureProtectedProbeTransport(Protocol):
    kind: str

    async def get_exact_once(
        self,
        *,
        url: str,
        bearer_token: bytearray,
        timeout_seconds: int,
        follow_redirects: bool,
    ) -> ProtectedProbeHttpResponse: ...

    async def close(self) -> None: ...


def _clear(buffer: object) -> bool:
    if type(buffer) is not bytearray:
        return False
    buffer[:] = b"\x00" * len(buffer)
    buffer.clear()
    return True


class FixtureOnlyProtectedProbeInvocationOwner:
    """Exercises the exact lifecycle while rejecting every real dependency."""

    __slots__ = ("_source", "_transport", "_used")

    def __init__(
        self,
        *,
        source: FixtureProtectedTokenSource,
        transport: FixtureProtectedProbeTransport,
    ) -> None:
        if (
            getattr(source, "kind", None) != "fixture-double"
            or not callable(getattr(source, "open", None))
            or not callable(getattr(source, "read_exact", None))
            or not callable(getattr(source, "close", None))
        ):
            raise TypeError("r1_probe_invocation_source_not_fixture_double")
        if (
            getattr(transport, "kind", None) != "fixture-double"
            or not callable(getattr(transport, "get_exact_once", None))
            or not callable(getattr(transport, "close", None))
        ):
            raise TypeError("r1_probe_invocation_transport_not_fixture_double")
        self._source: FixtureProtectedTokenSource | None = source
        self._transport: FixtureProtectedProbeTransport | None = transport
        self._used = False

    async def execute_once(
        self, authorization: str
    ) -> SanitizedFixtureInvocationResult:
        if self._used or authorization != FIXTURE_AUTHORIZATION:
            raise RuntimeError("r1_probe_invocation_reuse_or_auth_invalid")
        source, self._source = self._source, None
        transport, self._transport = self._transport, None
        if source is None or transport is None:
            raise RuntimeError("r1_probe_invocation_dependencies_unavailable")
        self._used = True

        source_reads = 0
        transport_calls = 0
        source_closed = False
        transport_closed = False
        secret_cleared = False
        token: object = None
        state = HELPER_FAILED
        close_failed = False
        try:
            await source.open()
            source_reads = 1
            token = await source.read_exact(REVIEW_TOKEN_NAME)
            if (
                type(token) is not bytearray
                or len(token) < 24
                or len(token) > 4096
                or b"\x00" in token
            ):
                raise ValueError("r1_probe_invocation_token_invalid")
            transport_calls = 1
            response = await transport.get_exact_once(
                url=PROBE_ENDPOINT,
                bearer_token=token,
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
            if type(response) is not ProtectedProbeHttpResponse:
                raise TypeError("r1_probe_invocation_response_invalid")
            state = evaluate_protected_probe_result(
                status_code=response.status_code,
                payload=response.payload,
                request_may_have_reached_host=False,
            ).value
        except BaseException:
            state = HELPER_FAILED
        finally:
            secret_cleared = _clear(token)
            try:
                await transport.close()
                transport_closed = True
            except BaseException:
                close_failed = True
            try:
                await source.close()
                source_closed = True
            except BaseException:
                close_failed = True
        if close_failed:
            state = HELPER_REMAINDER
        return SanitizedFixtureInvocationResult(
            state=state,
            credential_source_reads=source_reads,
            transport_calls=transport_calls,
            retries=0,
            redirects_followed=0,
            real_network_calls=0,
            secret_cleared=secret_cleared,
            source_closed=source_closed,
            transport_closed=transport_closed,
        )


__all__ = [
    "FIXTURE_AUTHORIZATION",
    "FixtureOnlyProtectedProbeInvocationOwner",
    "FixtureProbeHttpResponse",
    "ProtectedProbeHttpResponse",
    "PROBE_ENDPOINT",
    "REVIEW_TOKEN_NAME",
    "REQUEST_TIMEOUT_SECONDS",
    "SanitizedFixtureInvocationResult",
]
