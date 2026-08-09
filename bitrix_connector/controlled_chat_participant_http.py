"""HTTP OAuth inyectado para leer y ensayar participantes de Chat Test."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .bitrix_client import _remote_error_code, _validated_portal_url
from .controlled_chat_participant_adapter import (
    CONTROLLED_DEAL_ID,
    ChatParticipantMutation,
    ChatParticipantSnapshot,
    LinkedWork,
    OneShotControlledParticipantAdapter,
    ParticipantAdapterResult,
    ParticipantAdapterStatus,
    ParticipantSafetyState,
    controlled_participant_safety_ready,
)
from .openline_link_rehearsal import CONTROLLED_CHAT_ID, CONTROLLED_DIALOG_ID


BITRIX_CHAT_USER_LIST_METHOD = "im.chat.user.list"
BITRIX_CHAT_USER_LIST_PATH = "/rest/im.chat.user.list"
MAX_PARTICIPANT_LIST_PAGES = 20
_UNCERTAIN_CODES = {
    "QUERY_LIMIT_EXCEEDED",
    "INTERNAL_SERVER_ERROR",
    "ERROR_UNEXPECTED_ANSWER",
    "OVERLOAD_LIMIT",
}


class _ParticipantSafetyBlocked(Exception):
    pass


class _ParticipantListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: list[int]
    next: Optional[int] = None
    total: Optional[int] = None


class _ParticipantMutationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: int


class ParticipantHttpDecision(str, Enum):
    SUCCESS = "success"
    UNCERTAIN = "uncertain"
    FAIL = "fail"


@dataclass(frozen=True)
class ParticipantReadResult:
    decision: ParticipantHttpDecision
    snapshot: Optional[ChatParticipantSnapshot] = None
    error_code: Optional[str] = None
    http_status: Optional[int] = None
    pages: int = 0

    def __post_init__(self) -> None:
        if self.pages < 0 or self.pages > MAX_PARTICIPANT_LIST_PAGES:
            raise ValueError("participant_read_pages_invalid")
        if self.decision is ParticipantHttpDecision.SUCCESS:
            if self.snapshot is None or self.error_code is not None:
                raise ValueError("participant_read_success_invalid")
            return
        if self.snapshot is not None or not self.error_code:
            raise ValueError("participant_read_failure_invalid")


@dataclass(frozen=True)
class ParticipantMutationResult:
    decision: ParticipantHttpDecision
    error_code: Optional[str] = None
    http_status: Optional[int] = None

    def __post_init__(self) -> None:
        if self.decision is ParticipantHttpDecision.SUCCESS:
            if self.error_code is not None:
                raise ValueError("participant_mutation_success_invalid")
            return
        if not self.error_code:
            raise ValueError("participant_mutation_failure_invalid")


class BitrixChatParticipantReader:
    """Lee todos los IDs con im.chat.user.list; vacío nunca es autoritativo."""

    def __init__(
        self,
        *,
        portal_url: str,
        access_token: str,
        timeout_seconds: float,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        token = access_token.strip()
        if not token:
            raise ValueError("access_token no puede estar vacio")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        root = _validated_portal_url(portal_url)
        self._endpoint = f"{root}{BITRIX_CHAT_USER_LIST_PATH}"
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    def __repr__(self) -> str:
        return "BitrixChatParticipantReader(<redacted>)"

    async def read(self) -> ParticipantReadResult:
        start = 0
        seen_starts: set[int] = set()
        participants: set[int] = set()
        total: Optional[int] = None

        for page in range(1, MAX_PARTICIPANT_LIST_PAGES + 1):
            if start in seen_starts:
                return self._failed(
                    "participant_list_pagination_cycle", pages=page - 1
                )
            seen_starts.add(start)
            try:
                response = await self._http_client.post(
                    self._endpoint,
                    json={
                        "CHAT_ID": CONTROLLED_CHAT_ID,
                        "start": start,
                        "auth": self._access_token,
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError):
                return self._uncertain(
                    "participant_list_transport_uncertain", pages=page - 1
                )

            status = response.status_code
            remote_code = _remote_error_code(response)
            if (
                status in {408, 425, 429}
                or 500 <= status <= 599
                or remote_code in _UNCERTAIN_CODES
            ):
                return self._uncertain(
                    "participant_list_remote_uncertain",
                    status=status,
                    pages=page,
                )
            if remote_code is not None or not 200 <= status <= 299:
                return self._failed(
                    "participant_list_rejected",
                    status=status,
                    pages=page,
                )
            try:
                parsed = _ParticipantListResponse.model_validate(
                    response.json()
                )
            except (ValueError, ValidationError):
                return self._uncertain(
                    "participant_list_invalid_response",
                    status=status,
                    pages=page,
                )
            if not parsed.result:
                return self._failed(
                    "participant_list_empty_not_authoritative",
                    status=status,
                    pages=page,
                )
            if len(parsed.result) > 50:
                return self._uncertain(
                    "participant_list_page_size_invalid",
                    status=status,
                    pages=page,
                )
            page_ids = set(parsed.result)
            if (
                len(page_ids) != len(parsed.result)
                or any(item <= 0 for item in page_ids)
                or participants.intersection(page_ids)
            ):
                return self._uncertain(
                    "participant_list_identity_conflict",
                    status=status,
                    pages=page,
                )
            participants.update(page_ids)
            if parsed.total is not None:
                if parsed.total <= 0 or (total is not None and total != parsed.total):
                    return self._uncertain(
                        "participant_list_total_conflict",
                        status=status,
                        pages=page,
                    )
                total = parsed.total
            if parsed.next is None:
                if total is not None and total != len(participants):
                    return self._uncertain(
                        "participant_list_truncated",
                        status=status,
                        pages=page,
                    )
                return ParticipantReadResult(
                    decision=ParticipantHttpDecision.SUCCESS,
                    snapshot=ChatParticipantSnapshot(
                        crm_entity_id=CONTROLLED_DEAL_ID,
                        chat_id=CONTROLLED_CHAT_ID,
                        dialog_id=CONTROLLED_DIALOG_ID,
                        participant_ids=frozenset(participants),
                    ),
                    http_status=status,
                    pages=page,
                )
            if parsed.next <= start:
                return self._uncertain(
                    "participant_list_pagination_invalid",
                    status=status,
                    pages=page,
                )
            start = parsed.next

        return self._uncertain(
            "participant_list_page_limit_exceeded",
            pages=MAX_PARTICIPANT_LIST_PAGES,
        )

    @staticmethod
    def _uncertain(
        code: str,
        *,
        status: Optional[int] = None,
        pages: int,
    ) -> ParticipantReadResult:
        return ParticipantReadResult(
            decision=ParticipantHttpDecision.UNCERTAIN,
            error_code=code,
            http_status=status,
            pages=pages,
        )

    @staticmethod
    def _failed(
        code: str,
        *,
        status: Optional[int] = None,
        pages: int,
    ) -> ParticipantReadResult:
        return ParticipantReadResult(
            decision=ParticipantHttpDecision.FAIL,
            error_code=code,
            http_status=status,
            pages=pages,
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class BitrixControlledParticipantMutator:
    """Ejecuta sólo los contratos add/delete cerrados del adaptador."""

    def __init__(
        self,
        *,
        portal_url: str,
        access_token: str,
        timeout_seconds: float,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        token = access_token.strip()
        if not token:
            raise ValueError("access_token no puede estar vacio")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        self._root = _validated_portal_url(portal_url)
        self._access_token = token
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds
        )

    def __repr__(self) -> str:
        return "BitrixControlledParticipantMutator(<redacted>)"

    async def mutate(
        self, contract: ChatParticipantMutation
    ) -> ParticipantMutationResult:
        endpoint = f"{self._root}/rest/{contract.method}"
        payload = contract.payload.model_dump(mode="json")
        payload["auth"] = self._access_token
        try:
            response = await self._http_client.post(endpoint, json=payload)
        except (httpx.TimeoutException, httpx.TransportError):
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.UNCERTAIN,
                error_code="participant_mutation_transport_uncertain",
            )

        status = response.status_code
        remote_code = _remote_error_code(response)
        if (
            status in {408, 425, 429}
            or 500 <= status <= 599
            or remote_code in _UNCERTAIN_CODES
        ):
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.UNCERTAIN,
                error_code="participant_mutation_remote_uncertain",
                http_status=status,
            )
        if remote_code is not None or not 200 <= status <= 299:
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.FAIL,
                error_code="participant_mutation_rejected",
                http_status=status,
            )
        try:
            parsed = _ParticipantMutationResponse.model_validate(
                response.json()
            )
        except (ValueError, ValidationError):
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.UNCERTAIN,
                error_code="participant_mutation_invalid_response",
                http_status=status,
            )
        if parsed.result != CONTROLLED_CHAT_ID:
            return ParticipantMutationResult(
                decision=ParticipantHttpDecision.FAIL,
                error_code="participant_mutation_wrong_chat",
                http_status=status,
            )
        return ParticipantMutationResult(
            decision=ParticipantHttpDecision.SUCCESS,
            http_status=status,
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class InjectedParticipantOAuthProvider(Protocol):
    async def get_access_token(self, member_id: str) -> str: ...


class InjectedParticipantOAuthResources(Protocol):
    oauth_provider: InjectedParticipantOAuthProvider
    portal_url: str
    member_id: str

    async def close(self) -> None: ...


@dataclass
class ControlledParticipantHttpResources:
    reader: BitrixChatParticipantReader
    mutator: BitrixControlledParticipantMutator
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def build(
        cls,
        *,
        portal_url: str,
        access_token: str,
        timeout_seconds: float,
    ) -> "ControlledParticipantHttpResources":
        return cls(
            reader=BitrixChatParticipantReader(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            ),
            mutator=BitrixControlledParticipantMutator(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
            ),
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        first_error: Optional[BaseException] = None
        for client in (self.mutator, self.reader):
            try:
                await client.close()
            except BaseException as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error


async def rehearse_controlled_participant_with_injected_oauth(
    *,
    safety: ParticipantSafetyState,
    oauth_resources: InjectedParticipantOAuthResources,
    timeout_seconds: float,
    while_linked: Optional[LinkedWork] = None,
    http_resources_factory=ControlledParticipantHttpResources.build,
) -> ParticipantAdapterResult:
    """Compone lectura y mutación sin entorno, refresh, persistencia o retry."""

    resources: Optional[ControlledParticipantHttpResources] = None
    result = ParticipantAdapterResult(
        status=ParticipantAdapterStatus.BLOCKED,
        reason="controlled_participant_composition_failed_safe",
    )
    close_failed = False
    try:
        if timeout_seconds <= 0:
            raise ValueError("participant_timeout_invalid")
        if not controlled_participant_safety_ready(safety):
            raise _ParticipantSafetyBlocked
        token = await oauth_resources.oauth_provider.get_access_token(
            oauth_resources.member_id
        )
        resources = http_resources_factory(
            portal_url=oauth_resources.portal_url,
            access_token=token,
            timeout_seconds=timeout_seconds,
        )

        async def read_snapshot() -> ChatParticipantSnapshot:
            read = await resources.reader.read()
            if (
                read.decision is not ParticipantHttpDecision.SUCCESS
                or read.snapshot is None
            ):
                raise RuntimeError(
                    read.error_code or "participant_snapshot_unavailable"
                )
            return read.snapshot

        async def mutate(contract: ChatParticipantMutation) -> bool:
            mutation = await resources.mutator.mutate(contract)
            return mutation.decision is ParticipantHttpDecision.SUCCESS

        result = await OneShotControlledParticipantAdapter(
            safety=safety,
            read_snapshot=read_snapshot,
            mutate=mutate,
        ).rehearse(while_linked=while_linked)
    except _ParticipantSafetyBlocked:
        result = ParticipantAdapterResult(
            status=ParticipantAdapterStatus.BLOCKED,
            reason="controlled_participant_safety_barriers_invalid",
        )
    except Exception:
        pass
    finally:
        if resources is not None:
            try:
                await resources.close()
            except BaseException:
                close_failed = True
        try:
            await oauth_resources.close()
        except BaseException:
            close_failed = True

    if close_failed:
        return result.model_copy(
            update={
                "status": (
                    ParticipantAdapterStatus.FAILED_RESTORED
                    if result.rollback_verified
                    else ParticipantAdapterStatus.BLOCKED
                ),
                "reason": "controlled_participant_resource_close_failed",
            }
        )
    return result


__all__ = [
    "BITRIX_CHAT_USER_LIST_METHOD",
    "BITRIX_CHAT_USER_LIST_PATH",
    "MAX_PARTICIPANT_LIST_PAGES",
    "BitrixChatParticipantReader",
    "BitrixControlledParticipantMutator",
    "ControlledParticipantHttpResources",
    "InjectedParticipantOAuthResources",
    "ParticipantHttpDecision",
    "ParticipantMutationResult",
    "ParticipantReadResult",
    "rehearse_controlled_participant_with_injected_oauth",
]
