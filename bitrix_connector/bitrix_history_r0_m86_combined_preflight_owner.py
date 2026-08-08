"""M86-C: binding combinado real-ready con ejecución sólo hermética."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlsplit

import httpx

from .bitrix_history_r0_client import (
    BitrixHistoryR0Client,
    BitrixHistoryReadDecision,
)
from .bitrix_history_r0_m68_combined_preflight import (
    CombinedR1PreflightAdapter,
    InjectedClosedProbeResult,
)
from .bitrix_history_r0_m82_injected_settings_oauth_owner import (
    InjectedStoredOAuthBackend,
    M82Status,
    StoredOAuthAccessView,
    execute_m82_injected_settings_oauth_once,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    build_real_windows_credential_backend,
)
from .bitrix_history_r0_m86_real_https_factory import (
    AsyncClientFactory,
    build_real_m86_https_async_client,
)
from .bitrix_history_r0_m86_stored_oauth_backend import (
    build_real_m86_stored_oauth_backend,
)
from .bitrix_history_r0_preflight import (
    BitrixHistoryR0PreflightOutcome,
    build_bitrix_history_r0_preflight_from_dialog,
)
from .bitrix_history_r0_protected_settings_composition import (
    ProtectedSettingsLoader,
)
from .bitrix_history_r0_runner import CONTROLLED_CHAT_ID, CONTROLLED_DIALOG_ID
from .bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialBackend,
)
from .bot_v2_preflight import BitrixBotV2PreflightClient, BotV2PreflightInspector
from .config import ConnectorSettings, load_settings
from .openline_pilot_preflight import (
    BitrixOpenLinePreflightClient,
    OpenLineDialog,
    OpenLinePreflightInspector,
)


M86C_TIMEOUT_SECONDS = 10.0
M86C_HTTP_NAMES = ("preflight_bot", "preflight_dialog")
M86CFailureStage = Literal[
    "not_run",
    "none",
    "source_stage",
    "oauth_stage",
    "bot_stage",
    "bot_revision_stage",
    "bot_revision_transport_stage",
    "bot_revision_remote_stage",
    "bot_revision_token_expired_stage",
    "bot_revision_retryable_stage",
    "bot_revision_permanent_stage",
    "bot_revision_contract_stage",
    "bot_list_stage",
    "bot_contract_stage",
    "dialog_stage",
    "contract_stage",
    "cleanup_stage",
]


def _portal_origin(value: Optional[str]) -> str:
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
        raise ValueError("m86c_portal_origin_invalid")
    return candidate


@dataclass(frozen=True)
class M86CombinedPreflightSnapshot:
    phase: Literal["M86-C"]
    state: Literal["PREPARED", "VERIFIED", "NO-GO", "CANCELLED"]
    reason: str
    failure_stage: M86CFailureStage
    owner_calls: int
    credential_source_read_calls: int
    oauth_load_calls: int
    oauth_refresh_calls: Literal[0]
    oauth_token_view_reads: int
    http_client_factory_calls: int
    bot_read_calls: int
    openline_read_calls: int
    history_dialog_read_calls: int
    history_read_calls: Literal[0]
    resource_close_calls: int
    combined_preflight_verified: bool
    history_anchor_available: bool
    private_resources_closed: bool
    hermetic_execution: bool
    retry_budget: Literal[0] = 0
    messages_sent: Literal[0] = 0
    deletions_executed: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    remaining_real_bindings: Literal[2] = 2


class M86CombinedPreflightOwner:
    """Owner único: real-ready inerte o ejecución hermética inyectada."""

    __slots__ = (
        "_credential_backend",
        "_hermetic_execution",
        "_history_outcome",
        "_http_client_factory",
        "_oauth_backend",
        "_settings_loader",
        "_used",
    )

    def __init__(
        self,
        *,
        credential_backend: InjectedWindowsCredentialBackend,
        oauth_backend: InjectedStoredOAuthBackend,
        http_client_factory: AsyncClientFactory,
        hermetic_execution: bool,
        settings_loader: ProtectedSettingsLoader = load_settings,
    ) -> None:
        if (
            credential_backend is None
            or oauth_backend is None
            or not callable(http_client_factory)
            or type(hermetic_execution) is not bool
            or not callable(settings_loader)
        ):
            raise TypeError("m86c_owner_dependency_invalid")
        self._credential_backend: Optional[InjectedWindowsCredentialBackend] = (
            credential_backend
        )
        self._oauth_backend: Optional[InjectedStoredOAuthBackend] = oauth_backend
        self._http_client_factory: Optional[AsyncClientFactory] = http_client_factory
        self._settings_loader: Optional[ProtectedSettingsLoader] = settings_loader
        self._hermetic_execution = hermetic_execution
        self._history_outcome: Optional[BitrixHistoryR0PreflightOutcome] = None
        self._used = False

    def __repr__(self) -> str:
        return "M86CombinedPreflightOwner(<redacted>)"

    @staticmethod
    def _snapshot(
        *,
        state: Literal["PREPARED", "VERIFIED", "NO-GO", "CANCELLED"],
        reason: str,
        failure_stage: M86CFailureStage = "not_run",
        hermetic_execution: bool,
        owner_calls: int = 0,
        credential_source_read_calls: int = 0,
        oauth_load_calls: int = 0,
        oauth_token_view_reads: int = 0,
        http_client_factory_calls: int = 0,
        bot_read_calls: int = 0,
        openline_read_calls: int = 0,
        history_dialog_read_calls: int = 0,
        resource_close_calls: int = 0,
        combined_preflight_verified: bool = False,
        history_anchor_available: bool = False,
        private_resources_closed: bool = True,
    ) -> M86CombinedPreflightSnapshot:
        return M86CombinedPreflightSnapshot(
            phase="M86-C",
            state=state,
            reason=reason,
            failure_stage=failure_stage,
            owner_calls=owner_calls,
            credential_source_read_calls=credential_source_read_calls,
            oauth_load_calls=oauth_load_calls,
            oauth_refresh_calls=0,
            oauth_token_view_reads=oauth_token_view_reads,
            http_client_factory_calls=http_client_factory_calls,
            bot_read_calls=bot_read_calls,
            openline_read_calls=openline_read_calls,
            history_dialog_read_calls=history_dialog_read_calls,
            history_read_calls=0,
            resource_close_calls=resource_close_calls,
            combined_preflight_verified=combined_preflight_verified,
            history_anchor_available=history_anchor_available,
            private_resources_closed=private_resources_closed,
            hermetic_execution=hermetic_execution,
        )

    def preview(self) -> M86CombinedPreflightSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m86c_real_combined_preflight_bound_not_executed",
            hermetic_execution=False,
        )

    async def run_once(self) -> M86CombinedPreflightSnapshot:
        if not self._hermetic_execution:
            return self.preview()
        if self._used:
            self.clear()
            return self._snapshot(
                state="NO-GO",
                reason="m86c_owner_reuse_rejected",
                hermetic_execution=True,
                private_resources_closed=True,
            )
        self._used = True
        credential_backend, self._credential_backend = self._credential_backend, None
        oauth_backend, self._oauth_backend = self._oauth_backend, None
        http_factory, self._http_client_factory = self._http_client_factory, None
        settings_loader, self._settings_loader = self._settings_loader, None
        if (
            credential_backend is None
            or oauth_backend is None
            or http_factory is None
            or settings_loader is None
        ):
            return self._snapshot(
                state="NO-GO",
                reason="m86c_owner_dependencies_consumed",
                hermetic_execution=True,
                private_resources_closed=False,
            )

        http_calls = 0
        http_created = 0
        close_calls = 0
        close_failed = False
        combined_verified = False
        failure_stage: M86CFailureStage = "source_stage"
        bot_reads = 0
        line_reads = 0
        history_dialog_reads = 0

        async def operation(
            settings: ConnectorSettings,
            token_view: StoredOAuthAccessView,
        ) -> None:
            nonlocal http_calls, http_created, close_calls, close_failed
            nonlocal combined_verified
            nonlocal failure_stage
            nonlocal bot_reads, line_reads, history_dialog_reads
            failure_stage = "source_stage"
            portal_url = _portal_origin(settings.bitrix_domain)
            failure_stage = "oauth_stage"
            access_token = token_view.read_text()
            failure_stage = "bot_stage"

            async def make_http(name: str) -> httpx.AsyncClient:
                nonlocal http_calls, http_created
                if name not in M86C_HTTP_NAMES:
                    raise RuntimeError("m86c_http_name_invalid")
                http_calls += 1
                client = await http_factory(name, M86C_TIMEOUT_SECONDS)
                if not isinstance(client, httpx.AsyncClient):
                    raise TypeError("m86c_http_factory_result_invalid")
                http_created += 1
                return client

            async def close_pair(dependency: object, client: httpx.AsyncClient) -> None:
                nonlocal close_calls, close_failed
                close_calls += 1
                first_error: Optional[BaseException] = None
                try:
                    close_dependency = getattr(dependency, "close", None)
                    if callable(close_dependency):
                        await close_dependency()
                except BaseException as error:
                    first_error = error
                try:
                    await client.aclose()
                except BaseException as error:
                    first_error = first_error or error
                if first_error is not None:
                    close_failed = True
                    raise RuntimeError("m86c_preflight_resource_close_failed") from first_error

            async def bot_probe() -> InjectedClosedProbeResult:
                nonlocal bot_reads, failure_stage
                failure_stage = "bot_stage"
                client = await make_http("preflight_bot")
                dependency: Optional[BitrixBotV2PreflightClient] = None
                try:
                    dependency = BitrixBotV2PreflightClient(
                        portal_url=portal_url,
                        access_token=access_token,
                        timeout_seconds=M86C_TIMEOUT_SECONDS,
                        http_client=client,
                    )
                    def observe_bot_stage(stage: str) -> None:
                        nonlocal failure_stage
                        if stage not in (
                            "bot_revision_stage",
                            "bot_revision_transport_stage",
                            "bot_revision_remote_stage",
                            "bot_revision_token_expired_stage",
                            "bot_revision_retryable_stage",
                            "bot_revision_permanent_stage",
                            "bot_revision_contract_stage",
                            "bot_list_stage",
                            "bot_contract_stage",
                        ):
                            raise ValueError("m86c_bot_stage_invalid")
                        failure_stage = stage

                    result = await BotV2PreflightInspector(
                        dependency,
                        stage_observer=observe_bot_stage,
                    ).inspect()
                    bot_reads = 2
                    return InjectedClosedProbeResult(result)
                finally:
                    await close_pair(dependency, client)

            history_outcome: Optional[BitrixHistoryR0PreflightOutcome] = None

            async def openline_probe() -> InjectedClosedProbeResult:
                nonlocal line_reads, history_dialog_reads, history_outcome
                nonlocal failure_stage
                failure_stage = "dialog_stage"
                client = await make_http("preflight_dialog")
                line_dependency = BitrixOpenLinePreflightClient(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=M86C_TIMEOUT_SECONDS,
                    http_client=client,
                )
                history_dependency = BitrixHistoryR0Client(
                    portal_url=portal_url,
                    access_token=access_token,
                    timeout_seconds=M86C_TIMEOUT_SECONDS,
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
                        raise RuntimeError("m86c_combined_dialog_invalid")
                    history_dialog_reads = 1
                    result = await OpenLinePreflightInspector(
                        line_dependency
                    ).inspect_dialog(
                        dialog=OpenLineDialog(
                            id=dialog.id,
                            dialog_id=dialog.dialog_id,
                            entity_type=dialog.entity_type,
                            entity_id=dialog.entity_id,
                        ),
                        chat_id=CONTROLLED_CHAT_ID,
                        dialog_id=CONTROLLED_DIALOG_ID,
                    )
                    line_reads = 1
                    history_outcome = build_bitrix_history_r0_preflight_from_dialog(
                        settings=settings,
                        dialog=dialog,
                        resources_closed=True,
                    )
                    return InjectedClosedProbeResult(result)
                finally:
                    first_error: Optional[BaseException] = None
                    try:
                        await line_dependency.close()
                    except BaseException as error:
                        first_error = error
                    try:
                        await close_pair(history_dependency, client)
                    except BaseException as error:
                        first_error = first_error or error
                    if first_error is not None:
                        raise RuntimeError(
                            "m86c_combined_dialog_close_failed"
                        ) from first_error

            async def history_probe() -> InjectedClosedProbeResult:
                nonlocal failure_stage
                failure_stage = "contract_stage"
                if history_outcome is None:
                    raise RuntimeError("m86c_history_outcome_unavailable")
                return InjectedClosedProbeResult(history_outcome)

            adapter = CombinedR1PreflightAdapter(
                bot_probe=bot_probe,
                openline_probe=openline_probe,
                history_probe=history_probe,
            )
            try:
                await adapter.probe_once()
                failure_stage = "contract_stage"
                outcome = adapter.take_history_outcome_once()
                outcome.require_anchor()
                self._history_outcome = outcome
                combined_verified = True
            finally:
                adapter.clear()

        m82 = await execute_m82_injected_settings_oauth_once(
            credential_backend=credential_backend,
            oauth_backend=oauth_backend,
            operation=operation,
            settings_loader=settings_loader,
        )
        verified = (
            m82.status is M82Status.READY
            and combined_verified
            and self._history_outcome is not None
            and http_calls == 2
            and close_calls == 2
            and bot_reads == 2
            and line_reads == 1
            and history_dialog_reads == 1
            and m82.private_resources_closed
        )
        cancelled = m82.status is M82Status.CANCELLED
        if verified:
            failure_stage = "none"
        elif not m82.private_resources_closed or close_failed:
            failure_stage = "cleanup_stage"
        elif (
            m82.credential_source_read_calls != 7
            or m82.settings_load_calls == 0
            or m82.protected_failure_category
            == "protected_settings_validation_failed"
        ):
            failure_stage = "source_stage"
        elif m82.oauth_load_calls == 0 or m82.oauth_operation_calls == 0:
            failure_stage = "oauth_stage"
        if not verified:
            self.clear()
        return self._snapshot(
            state="VERIFIED" if verified else "CANCELLED" if cancelled else "NO-GO",
            reason=(
                "m86c_combined_preflight_verified_hermetically"
                if verified
                else "m86c_combined_preflight_cancelled"
                if cancelled
                else "m86c_combined_preflight_failed_safe"
            ),
            failure_stage=failure_stage,
            hermetic_execution=True,
            owner_calls=1,
            credential_source_read_calls=m82.credential_source_read_calls,
            oauth_load_calls=m82.oauth_load_calls,
            oauth_token_view_reads=m82.oauth_token_view_reads,
            http_client_factory_calls=http_calls,
            bot_read_calls=bot_reads,
            openline_read_calls=line_reads,
            history_dialog_read_calls=history_dialog_reads,
            resource_close_calls=close_calls,
            combined_preflight_verified=verified,
            history_anchor_available=verified,
            private_resources_closed=(
                m82.private_resources_closed
                and close_calls == http_created
                and not close_failed
            ),
        )

    def take_history_outcome_once(self) -> BitrixHistoryR0PreflightOutcome:
        outcome, self._history_outcome = self._history_outcome, None
        if outcome is None:
            raise RuntimeError("m86c_history_outcome_unavailable")
        return outcome

    def clear(self) -> None:
        self._history_outcome = None


def build_real_m86_combined_preflight_owner() -> M86CombinedPreflightOwner:
    """Compone M84/M86-A/M86-B sin abrir fuentes, OAuth, HTTP o red."""

    return M86CombinedPreflightOwner(
        credential_backend=build_real_windows_credential_backend(),
        oauth_backend=build_real_m86_stored_oauth_backend(),
        http_client_factory=build_real_m86_https_async_client,
        hermetic_execution=False,
    )


__all__ = [
    "M86CombinedPreflightOwner",
    "M86CombinedPreflightSnapshot",
    "M86CFailureStage",
    "M86C_HTTP_NAMES",
    "M86C_TIMEOUT_SECONDS",
    "build_real_m86_combined_preflight_owner",
]
