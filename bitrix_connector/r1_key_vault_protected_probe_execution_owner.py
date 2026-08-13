"""Real one-shot owner for the exact protected R1 probe operation."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .r1_key_vault_protected_probe_dotenv_source import (
    EXPECTED_DOTENV_PATH,
    ExactReviewTokenDotenvSource,
)
from .r1_key_vault_protected_probe_http_transport import (
    ExactOneShotProtectedProbeHttpTransport,
    ProtectedProbeTransportFailure,
    build_dormant_production_http_transport,
)
from .r1_key_vault_protected_probe_invocation_owner import (
    PROBE_ENDPOINT,
    REQUEST_TIMEOUT_SECONDS,
    REVIEW_TOKEN_NAME,
    ProtectedProbeHttpResponse,
)
from .r1_key_vault_protected_probe_invocation_policy import (
    ProtectedProbeInvocationState,
    evaluate_protected_probe_result,
)


REAL_CONFIRMATION = "EJECUTAR SONDA R1 PROTEGIDA UNA SOLA VEZ DESDE DOTENV EXACTO"
OWNER_MODULE = "bitrix_connector.r1_key_vault_protected_probe_execution_owner"
OWNER_COMMAND = (
    r'.\.venv\Scripts\python.exe -m '
    r'bitrix_connector.r1_key_vault_protected_probe_execution_owner '
    r'--confirm-code "EJECUTAR SONDA R1 PROTEGIDA UNA SOLA VEZ DESDE DOTENV EXACTO" '
    r'--dotenv-path .env'
)
SOURCE_FAILED = "NO-GO-PROTECTED-SOURCE-UNAVAILABLE"
OWNER_FAILED = "NO-GO-PROTECTED-PROBE-OWNER-FAILED"
REMAINDER = "NO-GO-REMAINDER"


@dataclass(frozen=True)
class ProtectedProbeExecutionSnapshot:
    state: str = OWNER_FAILED
    protected_source_opened: bool = False
    source_read_calls: int = 0
    request_calls: int = 0
    real_network_calls: int = 0
    retries: int = 0
    redirects_followed: int = 0
    token_cleared: bool = False
    source_closed: bool = False
    transport_closed: bool = False


def _clear(value: object) -> bool:
    if type(value) is not bytearray:
        return False
    value[:] = b"\x00" * len(value)
    value.clear()
    return True


async def execute_protected_probe_once(
    *,
    dotenv_path: Path,
    source: ExactReviewTokenDotenvSource | None = None,
    transport: ExactOneShotProtectedProbeHttpTransport | None = None,
) -> ProtectedProbeExecutionSnapshot:
    selected_source = source or ExactReviewTokenDotenvSource(dotenv_path)
    selected_transport = transport or build_dormant_production_http_transport()
    if type(selected_source) is not ExactReviewTokenDotenvSource:
        return ProtectedProbeExecutionSnapshot(state=SOURCE_FAILED)
    if type(selected_transport) is not ExactOneShotProtectedProbeHttpTransport:
        return ProtectedProbeExecutionSnapshot()

    source_opened = False
    source_reads = 0
    request_calls = 0
    network_calls = 0
    source_closed = False
    transport_closed = False
    token_cleared = False
    token: object = None
    state = OWNER_FAILED
    close_failed = False
    try:
        await selected_source.open()
        source_opened = True
        source_reads = 1
        token = await selected_source.read_exact(REVIEW_TOKEN_NAME)
        request_calls = 1
        network_calls = 1
        response = await selected_transport.get_exact_once(
            url=PROBE_ENDPOINT,
            bearer_token=token,
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        if type(response) is not ProtectedProbeHttpResponse:
            state = ProtectedProbeInvocationState.RESPONSE_DRIFT.value
        else:
            state = evaluate_protected_probe_result(
                status_code=response.status_code,
                payload=response.payload,
                request_may_have_reached_host=True,
            ).value
    except ProtectedProbeTransportFailure:
        state = ProtectedProbeInvocationState.AMBIGUOUS_CONSUMPTION.value
    except BaseException:
        state = SOURCE_FAILED if request_calls == 0 else OWNER_FAILED
    finally:
        token_cleared = _clear(token)
        try:
            await selected_transport.close()
            transport_closed = True
        except BaseException:
            close_failed = True
        try:
            await selected_source.close()
            source_closed = True
        except BaseException:
            close_failed = True
    if close_failed:
        state = REMAINDER
    return ProtectedProbeExecutionSnapshot(
        state=state,
        protected_source_opened=source_opened,
        source_read_calls=source_reads,
        request_calls=request_calls,
        real_network_calls=network_calls,
        token_cleared=token_cleared,
        source_closed=source_closed,
        transport_closed=transport_closed,
    )


Executor = Callable[..., Any]


def _parse_request(argv: Sequence[str]) -> Path | None:
    values = tuple(argv)
    if (
        len(values) != 4
        or values[0] != "--confirm-code"
        or values[1] != REAL_CONFIRMATION
        or values[2] != "--dotenv-path"
        or values[3] != ".env"
    ):
        return None
    return EXPECTED_DOTENV_PATH


def _emit(snapshot: ProtectedProbeExecutionSnapshot) -> None:
    print(json.dumps(asdict(snapshot), sort_keys=True))


def main(
    argv: Sequence[str] | None = None,
    *,
    executor: Executor = execute_protected_probe_once,
) -> int:
    selected = tuple(sys.argv[1:] if argv is None else argv)
    dotenv_path = _parse_request(selected)
    if dotenv_path is None:
        _emit(ProtectedProbeExecutionSnapshot(state="NO-GO-OWNER-REJECTED"))
        return 2
    try:
        snapshot = asyncio.run(executor(dotenv_path=dotenv_path))
        if type(snapshot) is not ProtectedProbeExecutionSnapshot:
            raise TypeError("r1_probe_execution_result_invalid")
    except KeyboardInterrupt:
        snapshot = ProtectedProbeExecutionSnapshot(state="CANCELLED")
    except BaseException:
        snapshot = ProtectedProbeExecutionSnapshot()
    _emit(snapshot)
    return 0 if snapshot.state in {
        ProtectedProbeInvocationState.VERIFIED_ABSENT.value,
        ProtectedProbeInvocationState.VERIFIED_PRESENT.value,
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OWNER_COMMAND",
    "OWNER_MODULE",
    "ProtectedProbeExecutionSnapshot",
    "REAL_CONFIRMATION",
    "execute_protected_probe_once",
    "main",
]
