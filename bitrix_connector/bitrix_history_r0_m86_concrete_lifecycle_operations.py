"""M86-I: operaciones concretas de preflight y M88 sobre recursos inyectados."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional
from urllib.parse import urlsplit

import httpx

from .bitrix_client import BitrixClient
from .bitrix_history_r0_client import (
    BitrixHistoryR0Client,
    BitrixHistoryReadDecision,
    BitrixSessionHistory,
)
from .bitrix_history_r0_exact_scope_composition import (
    run_exact_controlled_roundtrip_with_rollback,
)
from .bitrix_history_r0_m68_combined_preflight import (
    CombinedR1PreflightAdapter,
    InjectedClosedProbeResult,
)
from .bitrix_history_r0_m76_in_memory_concrete_builders import (
    ExactReplyDeleteClient,
)
from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)
from .bitrix_history_r0_preflight import (
    BitrixHistoryR0PreflightOutcome,
    build_bitrix_history_r0_preflight_from_dialog,
)
from .bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from .bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripStatus,
)
from .bitrix_history_r0_runner import CONTROLLED_CHAT_ID, CONTROLLED_DIALOG_ID
from .bitrix_webhook_event_roundtrip import (
    run_exact_controlled_webhook_event_roundtrip_with_rollback,
)
from .bot_v2_preflight import BitrixBotV2PreflightClient, BotV2PreflightInspector
from .config import ConnectorSettings
from .models import NormalizedBitrixEvent
from .nia_client import NiaClient
from .openline_pilot_preflight import (
    BitrixOpenLinePreflightClient,
    OpenLineDialog,
    OpenLinePreflightInspector,
)


M86I_TIMEOUT_SECONDS = 10.0
M86I_HTTP_NAMES = (
    "preflight_bot",
    "preflight_dialog",
    "nia",
    "bitrix",
    "deleter",
    "roundtrip_history",
)

AsyncClientFactory = Callable[[str, float], Awaitable[httpx.AsyncClient]]
CrossTurnWaiter = Callable[
    [ConnectorSettings, StoredOAuthAccessView, BitrixHistoryR0PreflightOutcome],
    Awaitable[None],
]


def _https_origin(value: Optional[str], *, reason: str) -> str:
    candidate = (value or "").strip().rstrip("/")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(reason)
    return candidate


def _history_envelope(history: BitrixSessionHistory, *, indexed: bool) -> object:
    messages = [item.model_dump(mode="json") for item in history.messages]
    users = [item.model_dump(mode="json") for item in history.users]
    return {
        "result": {
            "chatId": history.chat_id,
            "sessionId": history.session_id,
            "message": (
                {str(item["id"]): item for item in messages}
                if indexed
                else messages
            ),
            "users": users,
        }
    }


class _SequentialHistoryReader:
    """Adapta tres lecturas máximas sin conservar cuerpos ni textos."""

    def __init__(
        self,
        dependency: BitrixHistoryR0Client,
        *,
        input_supplied_by_event: bool = False,
    ) -> None:
        self._dependency: Optional[BitrixHistoryR0Client] = dependency
        self.calls = 0
        self._input_supplied_by_event = input_supplied_by_event

    async def _read(self, session_id: int, *, indexed: bool) -> object:
        if self._dependency is None or self.calls >= 3:
            raise RuntimeError("m86i_history_reader_reuse_rejected")
        self.calls += 1
        result = await self._dependency.get_session_history(session_id)
        if (
            result.decision is not BitrixHistoryReadDecision.SUCCESS
            or result.history is None
            or result.history.session_id != session_id
            or result.history.chat_id != CONTROLLED_CHAT_ID
        ):
            raise RuntimeError("m86i_history_read_invalid")
        return _history_envelope(result.history, indexed=indexed)

    async def read_post_anchor_history(self, *, session_id: int) -> object:
        if self._input_supplied_by_event or self.calls != 0:
            raise RuntimeError("m86i_post_anchor_order_invalid")
        return await self._read(session_id, indexed=False)

    async def read_post_send_history(self, *, session_id: int) -> object:
        expected = 0 if self._input_supplied_by_event else 1
        if self.calls != expected:
            raise RuntimeError("m86i_post_send_order_invalid")
        return await self._read(session_id, indexed=True)

    async def read_post_delete_history(self, *, session_id: int) -> object:
        expected = 1 if self._input_supplied_by_event else 2
        if self.calls != expected:
            raise RuntimeError("m86i_post_delete_order_invalid")
        return await self._read(session_id, indexed=True)

    def clear(self) -> None:
        self._dependency = None


class _CountingNiaSender:
    def __init__(self, dependency: NiaClient) -> None:
        self._dependency = dependency
        self.calls = 0

    async def send_approved_text(self, payload):
        if self.calls != 0:
            raise RuntimeError("m86i_nia_sender_reuse_rejected")
        self.calls = 1
        return await self._dependency.send_approved_text(payload)


class _CountingBitrixSender:
    def __init__(self, dependency: BitrixClient) -> None:
        self._dependency = dependency
        self.calls = 0

    async def send_approved_message(self, payload):
        if self.calls != 0:
            raise RuntimeError("m86i_bitrix_sender_reuse_rejected")
        self.calls = 1
        return await self._dependency.send_approved_message(payload)


@dataclass(frozen=True)
class M86ConcreteM88Result:
    phase: Literal["M86-I"]
    state: Literal["VERIFIED", "ROLLED-BACK", "NO-GO"]
    reason: str
    http_client_factory_calls: int
    history_read_calls: int
    nia_call_count: int
    bitrix_send_call_count: int
    delete_call_count: int
    resource_close_calls: int
    private_resources_closed: bool
    concrete_clients_used: Literal[True] = True
    transport_injected: Literal[True] = True
    retry_budget: Literal[0] = 0
    oauth_refresh_calls: Literal[0] = 0
    payload_retained: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86ConcreteLifecycleOperations:
    """Consume operaciones reales una vez usando sólo transporte inyectado."""

    def __init__(
        self,
        *,
        nia_base_url: str,
        http_client_factory: AsyncClientFactory,
        cross_turn_waiter: CrossTurnWaiter,
        expected_sender_id: Optional[int] = None,
        emergency_rollback: bool = False,
    ) -> None:
        if (
            not callable(http_client_factory)
            or not callable(cross_turn_waiter)
            or (expected_sender_id is not None and expected_sender_id <= 0)
            or type(emergency_rollback) is not bool
        ):
            raise TypeError("m86i_operations_dependency_invalid")
        self._nia_base_url: Optional[str] = _https_origin(
            nia_base_url, reason="m86i_nia_origin_invalid"
        )
        self._http_client_factory: Optional[AsyncClientFactory] = http_client_factory
        self._cross_turn_waiter: Optional[CrossTurnWaiter] = cross_turn_waiter
        self._expected_sender_id = expected_sender_id
        self._emergency_rollback = emergency_rollback
        self._outcome_identity: Optional[int] = None
        self._preflight_used = False
        self._cross_turn_used = False
        self._m88_used = False

    def __repr__(self) -> str:
        return "M86ConcreteLifecycleOperations(<redacted>)"

    async def _make_http(self, name: str) -> httpx.AsyncClient:
        factory = self._http_client_factory
        if factory is None or name not in M86I_HTTP_NAMES:
            raise RuntimeError("m86i_http_factory_unavailable")
        client = await factory(name, M86I_TIMEOUT_SECONDS)
        if not isinstance(client, httpx.AsyncClient):
            raise TypeError("m86i_http_factory_result_invalid")
        return client

    @staticmethod
    async def _close_pair(dependency: object, client: httpx.AsyncClient) -> None:
        first_error: Optional[BaseException] = None
        try:
            method = getattr(dependency, "close", None)
            if callable(method):
                await method()
        except BaseException as error:
            first_error = error
        try:
            await client.aclose()
        except BaseException as error:
            first_error = first_error or error
        if first_error is not None:
            raise RuntimeError("m86i_resource_close_failed") from first_error

    async def preflight(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
    ) -> BitrixHistoryR0PreflightOutcome:
        if self._preflight_used:
            raise RuntimeError("m86i_preflight_reuse_rejected")
        self._preflight_used = True
        portal_url = _https_origin(
            settings.bitrix_domain, reason="m86i_portal_origin_invalid"
        )
        access_token = token_view.read_text()

        async def bot_probe() -> InjectedClosedProbeResult:
            client = await self._make_http("preflight_bot")
            dependency = BitrixBotV2PreflightClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=client,
            )
            try:
                return InjectedClosedProbeResult(
                    await BotV2PreflightInspector(dependency).inspect()
                )
            finally:
                await self._close_pair(dependency, client)

        history_outcome: Optional[BitrixHistoryR0PreflightOutcome] = None

        async def openline_probe() -> InjectedClosedProbeResult:
            nonlocal history_outcome
            client = await self._make_http("preflight_dialog")
            line_dependency = BitrixOpenLinePreflightClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=client,
            )
            history_dependency = BitrixHistoryR0Client(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=client,
            )
            try:
                dialog_read = await history_dependency.get_dialog(
                    CONTROLLED_DIALOG_ID
                )
                dialog = dialog_read.dialog
                if (
                    dialog_read.decision is not BitrixHistoryReadDecision.SUCCESS
                    or dialog is None
                    or not dialog.entity_id
                ):
                    raise RuntimeError("m86i_combined_dialog_invalid")
                openline_dialog = OpenLineDialog(
                    id=dialog.id,
                    dialog_id=dialog.dialog_id,
                    entity_type=dialog.entity_type,
                    entity_id=dialog.entity_id,
                )
                line_result = await OpenLinePreflightInspector(
                    line_dependency
                ).inspect_dialog(
                    dialog=openline_dialog,
                    chat_id=CONTROLLED_CHAT_ID,
                    dialog_id=CONTROLLED_DIALOG_ID,
                )
                history_outcome = build_bitrix_history_r0_preflight_from_dialog(
                    settings=settings,
                    dialog=dialog,
                    resources_closed=True,
                )
                return InjectedClosedProbeResult(
                    line_result
                )
            finally:
                first_error: Optional[BaseException] = None
                try:
                    await line_dependency.close()
                except BaseException as error:
                    first_error = error
                try:
                    await self._close_pair(history_dependency, client)
                except BaseException as error:
                    first_error = first_error or error
                if first_error is not None:
                    raise RuntimeError("m86i_combined_dialog_close_failed") from first_error

        async def history_probe() -> InjectedClosedProbeResult:
            if history_outcome is None:
                raise RuntimeError("m86i_combined_history_outcome_unavailable")
            return InjectedClosedProbeResult(history_outcome)

        adapter = CombinedR1PreflightAdapter(
            bot_probe=bot_probe,
            openline_probe=openline_probe,
            history_probe=history_probe,
        )
        try:
            await adapter.probe_once()
            outcome = adapter.take_history_outcome_once()
            outcome.require_anchor()
            self._outcome_identity = id(outcome)
            return outcome
        finally:
            access_token = ""
            adapter.clear()

    async def cross_turn(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
        outcome: BitrixHistoryR0PreflightOutcome,
    ) -> None:
        waiter, self._cross_turn_waiter = self._cross_turn_waiter, None
        if (
            self._cross_turn_used
            or waiter is None
            or id(outcome) != self._outcome_identity
        ):
            raise RuntimeError("m86i_cross_turn_reuse_or_identity_invalid")
        self._cross_turn_used = True
        await waiter(settings, token_view, outcome)

    async def m88(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
        outcome: BitrixHistoryR0PreflightOutcome,
    ) -> M86ConcreteM88Result:
        if (
            self._m88_used
            or not self._cross_turn_used
            or id(outcome) != self._outcome_identity
            or self._nia_base_url is None
        ):
            raise RuntimeError("m86i_m88_reuse_or_identity_invalid")
        self._m88_used = True
        portal_url = _https_origin(
            settings.bitrix_domain, reason="m86i_portal_origin_invalid"
        )
        access_token = token_view.read_text()
        resources: list[tuple[object, httpx.AsyncClient]] = []
        history_reader: Optional[_SequentialHistoryReader] = None
        nia_sender: Optional[_CountingNiaSender] = None
        bitrix_sender: Optional[_CountingBitrixSender] = None
        composed = None
        close_calls = 0
        close_failed = False
        try:
            nia_http = await self._make_http("nia")
            nia = NiaClient(
                base_url=self._nia_base_url,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=nia_http,
            )
            resources.append((nia, nia_http))

            bitrix_http = await self._make_http("bitrix")
            bitrix = BitrixClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=bitrix_http,
            )
            resources.append((bitrix, bitrix_http))

            delete_http = await self._make_http("deleter")
            deleter = ExactReplyDeleteClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=delete_http,
            )
            resources.append((deleter, delete_http))

            history_http = await self._make_http("roundtrip_history")
            history = BitrixHistoryR0Client(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=history_http,
            )
            resources.append((history, history_http))
            history_reader = _SequentialHistoryReader(history)
            nia_sender = _CountingNiaSender(nia)
            bitrix_sender = _CountingBitrixSender(bitrix)

            anchor = outcome.require_anchor()
            payload = await history_reader.read_post_anchor_history(
                session_id=anchor.session_id
            )
            try:
                composed = await run_exact_controlled_roundtrip_with_rollback(
                    plan=build_protected_real_roundtrip_plan(),
                    preflight=outcome,
                    payload=payload,
                    nia_sender=nia_sender,
                    bitrix_sender=bitrix_sender,
                    post_send_history_reader=history_reader,
                    deleter=deleter,
                    post_delete_history_reader=history_reader,
                    expected_sender_id=self._expected_sender_id,
                    emergency_rollback=self._emergency_rollback,
                )
            finally:
                payload = None
        finally:
            if history_reader is not None:
                history_reader.clear()
            for dependency, client in reversed(resources):
                close_calls += 1
                try:
                    await self._close_pair(dependency, client)
                except BaseException:
                    close_failed = True
            access_token = ""
            self._nia_base_url = None
            self._http_client_factory = None
            self._outcome_identity = None

        status = getattr(composed, "status", None)
        state = (
            "VERIFIED"
            if status is ComposedRoundtripStatus.VERIFIED
            else "ROLLED-BACK"
            if status is ComposedRoundtripStatus.ROLLED_BACK
            else "NO-GO"
        )
        if close_failed:
            state = "NO-GO"
        return M86ConcreteM88Result(
            phase="M86-I",
            state=state,
            reason=(
                "m86i_concrete_roundtrip_verified_hermetically"
                if state == "VERIFIED"
                else "m86i_concrete_roundtrip_rolled_back_hermetically"
                if state == "ROLLED-BACK"
                else "m86i_concrete_roundtrip_failed_safe"
            ),
            http_client_factory_calls=len(resources),
            history_read_calls=history_reader.calls if history_reader else 0,
            nia_call_count=nia_sender.calls if nia_sender else 0,
            bitrix_send_call_count=bitrix_sender.calls if bitrix_sender else 0,
            delete_call_count=getattr(composed, "delete_call_count", 0),
            resource_close_calls=close_calls,
            private_resources_closed=(close_calls == len(resources) and not close_failed),
        )

    async def m88_event(
        self,
        settings: ConnectorSettings,
        token_view: StoredOAuthAccessView,
        outcome: BitrixHistoryR0PreflightOutcome,
        event: NormalizedBitrixEvent,
    ) -> M86ConcreteM88Result:
        """Variante webhook: el evento exacto sustituye la lectura de entrada."""

        if (
            self._m88_used
            or self._cross_turn_used
            or id(outcome) != self._outcome_identity
            or self._nia_base_url is None
            or not isinstance(event, NormalizedBitrixEvent)
        ):
            raise RuntimeError("m86i_event_m88_reuse_or_identity_invalid")
        self._cross_turn_used = True
        self._m88_used = True
        portal_url = _https_origin(
            settings.bitrix_domain, reason="m86i_portal_origin_invalid"
        )
        access_token = token_view.read_text()
        resources: list[tuple[object, httpx.AsyncClient]] = []
        history_reader: Optional[_SequentialHistoryReader] = None
        nia_sender: Optional[_CountingNiaSender] = None
        bitrix_sender: Optional[_CountingBitrixSender] = None
        composed = None
        close_calls = 0
        close_failed = False
        try:
            nia_http = await self._make_http("nia")
            nia = NiaClient(
                base_url=self._nia_base_url,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=nia_http,
            )
            resources.append((nia, nia_http))

            bitrix_http = await self._make_http("bitrix")
            bitrix = BitrixClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=bitrix_http,
            )
            resources.append((bitrix, bitrix_http))

            delete_http = await self._make_http("deleter")
            deleter = ExactReplyDeleteClient(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=delete_http,
            )
            resources.append((deleter, delete_http))

            history_http = await self._make_http("roundtrip_history")
            history = BitrixHistoryR0Client(
                portal_url=portal_url,
                access_token=access_token,
                timeout_seconds=M86I_TIMEOUT_SECONDS,
                http_client=history_http,
            )
            resources.append((history, history_http))
            history_reader = _SequentialHistoryReader(
                history,
                input_supplied_by_event=True,
            )
            nia_sender = _CountingNiaSender(nia)
            bitrix_sender = _CountingBitrixSender(bitrix)
            composed = (
                await run_exact_controlled_webhook_event_roundtrip_with_rollback(
                    plan=build_protected_real_roundtrip_plan(),
                    preflight=outcome,
                    event=event,
                    nia_sender=nia_sender,
                    bitrix_sender=bitrix_sender,
                    post_send_history_reader=history_reader,
                    deleter=deleter,
                    post_delete_history_reader=history_reader,
                    emergency_rollback=self._emergency_rollback,
                )
            )
        finally:
            if history_reader is not None:
                history_reader.clear()
            for dependency, client in reversed(resources):
                close_calls += 1
                try:
                    await self._close_pair(dependency, client)
                except BaseException:
                    close_failed = True
            access_token = ""
            self._nia_base_url = None
            self._http_client_factory = None
            self._outcome_identity = None

        status = getattr(composed, "status", None)
        state = (
            "VERIFIED"
            if status is ComposedRoundtripStatus.VERIFIED
            else "ROLLED-BACK"
            if status is ComposedRoundtripStatus.ROLLED_BACK
            else "NO-GO"
        )
        if close_failed:
            state = "NO-GO"
        return M86ConcreteM88Result(
            phase="M86-I",
            state=state,
            reason=(
                "m86i_concrete_roundtrip_verified_hermetically"
                if state == "VERIFIED"
                else "m86i_concrete_roundtrip_rolled_back_hermetically"
                if state == "ROLLED-BACK"
                else "m86i_concrete_roundtrip_failed_safe"
            ),
            http_client_factory_calls=len(resources),
            history_read_calls=history_reader.calls if history_reader else 0,
            nia_call_count=nia_sender.calls if nia_sender else 0,
            bitrix_send_call_count=bitrix_sender.calls if bitrix_sender else 0,
            delete_call_count=getattr(composed, "delete_call_count", 0),
            resource_close_calls=close_calls,
            private_resources_closed=(
                close_calls == len(resources) and not close_failed
            ),
        )


__all__ = [
    "M86ConcreteLifecycleOperations",
    "M86ConcreteM88Result",
    "M86I_HTTP_NAMES",
    "M86I_TIMEOUT_SECONDS",
]
