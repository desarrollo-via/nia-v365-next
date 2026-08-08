"""M85: owner/comando final dormido y dictamen previo a la primera confirmación."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

from .bitrix_history_r0_dormant_confirmation_coordinator import (
    DormantTwoConfirmationCoordinator,
    InjectedConfirmation,
    InjectedFreshPreflightEvidence,
    InjectedManualRemovalEvidence,
    FIRST_CONFIRMATION_SCOPE,
    MANUAL_REMOVAL_SCOPE,
    SECOND_CONFIRMATION_SCOPE,
)
from .bitrix_history_r0_m63_literal_parser import (
    M63_MANUAL_REMOVAL_TEXT,
    M63_SECOND_CONFIRMATION_TEXT,
)
from .bitrix_history_r0_m73_single_fixture_owner import (
    InjectedFixtureAttentionEvidence,
)
from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_M63_SOURCE_CLAUSE_REPLACEMENT,
)
from .bitrix_history_r0_m83_injected_https_owner import (
    M83HttpsOwnerSnapshot,
    M83Status,
)
from .bitrix_history_r0_m84_windows_credential_backend import (
    M84BackendContractSnapshot,
)
from .bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from .bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
)


M85_FIRST_CONFIRMATION_TEXT = (
    "PRIMERA CONFIRMACIÓN R1 — PREFLIGHT Y PREPARACIÓN: Autorizo exclusivamente "
    "preparar una única prueba sobre chat_id=78733, dialog_id=chat78733 y bot "
    "373259, con una eventual respuesta Bitrix y rollback exacto limitado al ID "
    "devuelto por ese envío. "
    + M80_M63_SOURCE_CLAUSE_REPLACEMENT
    + " obtener una vez el OAuth almacenado sin renovarlo; y ejecutar como "
    "máximo una lectura de imbot.v2.Revision.get, imbot.v2.Bot.list, "
    "imopenlines.config.get para Línea 13 e imopenlines.dialog.get para "
    "chat78733. No autorizo historial, llamada NIA, envío, borrado, otro mensaje, "
    "reintento ni cambio productivo. Cualquier deriva o cierre ambiguo consume "
    "la autorización y termina en NO-GO."
)
M85_MANUAL_REMOVAL_TEXT = M63_MANUAL_REMOVAL_TEXT
M85_SECOND_CONFIRMATION_TEXT = M63_SECOND_CONFIRMATION_TEXT

M85_MISSING_REAL_BINDINGS = (
    "stored_oauth_backend_real_binding_unbound",
    "real_https_transport_factory_unbound",
    "fresh_combined_preflight_real_binding_unbound",
    "cross_turn_manual_second_confirmation_and_attention_channel_unbound",
    "source_bound_executable_command_unbound",
)


@dataclass(frozen=True)
class M85FinalCommandContract:
    phase: Literal["M85"] = "M85"
    command_name: Literal["nia-next-r1-one-shot-final"] = (
        "nia-next-r1-one-shot-final"
    )
    sequence: tuple[str, ...] = (
        "first_confirmation",
        "protected_source_and_stored_oauth",
        "fresh_preflight",
        "manual_removal_evidence",
        "second_confirmation",
        "waiting_message_attention",
        "same_chat_roundtrip_or_exact_rollback",
        "terminal_cleanup",
    )
    first_and_second_confirmations_separate: Literal[True] = True
    first_confirmation_uses_credential_manager: Literal[True] = True
    first_confirmation_uses_dotenv: Literal[False] = False
    maximum_timeout_seconds: Literal[300] = 300
    retry_budget: Literal[0] = 0
    default_execution_enabled: Literal[False] = False
    cli_available: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False


M85_FINAL_COMMAND_CONTRACT = M85FinalCommandContract()


InjectedTextReader = Callable[[], Awaitable[str]]
PreflightProbe = Callable[[], Awaitable[InjectedFreshPreflightEvidence]]
AttentionProbe = Callable[[], Awaitable[InjectedFixtureAttentionEvidence]]
ExactScopeProbe = Callable[[], Awaitable[ComposedRoundtripResult]]
CleanupCallback = Callable[[], None]


class _M85LiteralParser:
    __slots__ = ("_reader", "_stage")

    def __init__(self, reader: InjectedTextReader) -> None:
        self._reader: Optional[InjectedTextReader] = reader
        self._stage = 0

    async def _take(self, expected: str, stage: int) -> None:
        reader = self._reader
        if reader is None or self._stage != stage:
            self.clear()
            raise RuntimeError("m85_literal_order_or_reuse_invalid")
        try:
            value = await reader()
            if type(value) is not str or value != expected:
                raise ValueError("m85_literal_mismatch")
            self._stage += 1
        except BaseException:
            self.clear()
            raise

    async def read_first(self) -> InjectedConfirmation:
        await self._take(M85_FIRST_CONFIRMATION_TEXT, 0)
        return InjectedConfirmation(True, FIRST_CONFIRMATION_SCOPE)

    async def read_manual(self) -> InjectedManualRemovalEvidence:
        await self._take(M85_MANUAL_REMOVAL_TEXT, 1)
        return InjectedManualRemovalEvidence(True, MANUAL_REMOVAL_SCOPE)

    async def read_second(self) -> InjectedConfirmation:
        await self._take(M85_SECOND_CONFIRMATION_TEXT, 2)
        result = InjectedConfirmation(True, SECOND_CONFIRMATION_SCOPE)
        self.clear()
        return result

    def clear(self) -> None:
        self._reader = None
        self._stage = -1


@dataclass(frozen=True)
class M85FinalCommandSnapshot:
    phase: Literal["M85"]
    state: Literal["PREPARED", "REHEARSED", "NO-GO", "CANCELLED"]
    reason: str
    execution_requested: bool
    owner_calls: int
    literal_read_calls: int
    preflight_calls: int
    attention_calls: int
    exact_scope_calls: int
    cleanup_calls: int
    m83_verified: bool
    m84_implemented_not_read: bool
    two_confirmations_separated: bool
    sequence_rehearsed: bool
    private_state_cleared: bool
    missing_real_bindings: tuple[str, ...] = M85_MISSING_REAL_BINDINGS
    missing_real_binding_count: Literal[5] = 5
    first_confirmation_decision: Literal["DO-NOT-REQUEST"] = "DO-NOT-REQUEST"
    first_confirmation_request_ready: Literal[False] = False
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    retry_budget: Literal[0] = 0
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M85DormantFinalCommandOwner:
    """Ensaya la secuencia final una vez; preview y defaults nunca ejecutan."""

    __slots__ = ("_dependencies", "_used")

    def __init__(
        self,
        *,
        m83_snapshot: M83HttpsOwnerSnapshot,
        m84_snapshot: M84BackendContractSnapshot,
        text_reader: InjectedTextReader,
        preflight_probe: PreflightProbe,
        attention_probe: AttentionProbe,
        exact_scope_probe: ExactScopeProbe,
        cleanup: CleanupCallback,
        timeout_seconds: float = 300.0,
    ) -> None:
        dependencies = (
            text_reader,
            preflight_probe,
            attention_probe,
            exact_scope_probe,
            cleanup,
        )
        if (
            type(m83_snapshot) is not M83HttpsOwnerSnapshot
            or m83_snapshot.status is not M83Status.VERIFIED
            or m83_snapshot.http_resource_factory_calls != 4
            or m83_snapshot.oauth_refresh_calls != 0
            or not m83_snapshot.all_private_resources_closed
            or type(m84_snapshot) is not M84BackendContractSnapshot
            or m84_snapshot.state != "IMPLEMENTED-NOT-READ"
            or m84_snapshot.real_credential_reads != 0
            or any(not callable(item) for item in dependencies)
            or timeout_seconds <= 0
            or timeout_seconds > 300
        ):
            raise ValueError("m85_final_command_owner_invalid")
        self._dependencies: Optional[tuple[object, ...]] = (
            m83_snapshot,
            m84_snapshot,
            *dependencies,
            timeout_seconds,
        )
        self._used = False

    def __repr__(self) -> str:
        return "M85DormantFinalCommandOwner(<redacted>)"

    @staticmethod
    def _snapshot(
        *,
        state: Literal["PREPARED", "REHEARSED", "NO-GO", "CANCELLED"],
        reason: str,
        execution_requested: bool,
        owner_calls: int = 0,
        literal_read_calls: int = 0,
        preflight_calls: int = 0,
        attention_calls: int = 0,
        exact_scope_calls: int = 0,
        cleanup_calls: int = 0,
        sequence_rehearsed: bool = False,
        private_state_cleared: bool = True,
    ) -> M85FinalCommandSnapshot:
        return M85FinalCommandSnapshot(
            phase="M85",
            state=state,
            reason=reason,
            execution_requested=execution_requested,
            owner_calls=owner_calls,
            literal_read_calls=literal_read_calls,
            preflight_calls=preflight_calls,
            attention_calls=attention_calls,
            exact_scope_calls=exact_scope_calls,
            cleanup_calls=cleanup_calls,
            m83_verified=True,
            m84_implemented_not_read=True,
            two_confirmations_separated=True,
            sequence_rehearsed=sequence_rehearsed,
            private_state_cleared=private_state_cleared,
        )

    def preview(self) -> M85FinalCommandSnapshot:
        return self._snapshot(
            state="PREPARED",
            reason="m85_final_command_prepared_inert",
            execution_requested=False,
        )

    async def run_once(self, *, execute: bool = False) -> M85FinalCommandSnapshot:
        if not execute:
            return self.preview()
        if self._used or self._dependencies is None:
            self._used = True
            self._dependencies = None
            return self._snapshot(
                state="NO-GO",
                reason="m85_final_command_reuse_rejected",
                execution_requested=True,
                owner_calls=0,
            )
        self._used = True
        dependencies, self._dependencies = self._dependencies, None
        parser: _M85LiteralParser | None = None
        literal_calls = 0
        preflight_calls = 0
        attention_calls = 0
        exact_calls = 0
        cleanup_calls = 0
        state: Literal["REHEARSED", "NO-GO", "CANCELLED"] = "NO-GO"
        reason = "m85_final_command_rehearsal_failed_safe"
        try:
            (
                _m83,
                _m84,
                text_reader,
                preflight_probe,
                attention_probe,
                exact_scope_probe,
                cleanup,
                timeout_seconds,
            ) = dependencies

            async def counted_text_reader() -> str:
                nonlocal literal_calls
                literal_calls += 1
                return await text_reader()

            parser = _M85LiteralParser(counted_text_reader)

            async def preflight() -> InjectedFreshPreflightEvidence:
                nonlocal preflight_calls
                preflight_calls += 1
                return await preflight_probe()

            async def exact_with_attention() -> ComposedRoundtripResult:
                nonlocal attention_calls, exact_calls
                attention_calls += 1
                evidence = await attention_probe()
                if (
                    type(evidence) is not InjectedFixtureAttentionEvidence
                    or evidence.state != "WAITING-MESSAGE"
                    or not evidence.fixture_attention_emitted
                    or not evidence.fixture_message_signal_received
                    or evidence.external_calls != 0
                ):
                    raise ValueError("m85_attention_rehearsal_invalid")
                exact_calls += 1
                return await exact_scope_probe()

            coordinator = DormantTwoConfirmationCoordinator(
                plan=build_protected_real_roundtrip_plan(),
                first_confirmation_reader=parser.read_first,
                preflight_probe=preflight,
                manual_evidence_reader=parser.read_manual,
                second_confirmation_reader=parser.read_second,
                exact_scope_probe=exact_with_attention,
                timeout_seconds=timeout_seconds,
            )
            result = await coordinator.run_once()
            if result.state == "PREPARED":
                state = "REHEARSED"
                reason = "m85_final_command_sequence_rehearsed_in_doubles"
            elif result.state == "CANCELLED":
                state = "CANCELLED"
                reason = "m85_final_command_rehearsal_cancelled"
        except asyncio.CancelledError:
            state = "CANCELLED"
            reason = "m85_final_command_rehearsal_cancelled"
        except BaseException:
            pass
        finally:
            if parser is not None:
                parser.clear()
            try:
                cleanup()
                cleanup_calls = 1
            except BaseException:
                state = "NO-GO"
                reason = "m85_final_command_cleanup_failed"
            dependencies = ()
        return self._snapshot(
            state=state,
            reason=reason,
            execution_requested=True,
            owner_calls=1,
            literal_read_calls=literal_calls,
            preflight_calls=preflight_calls,
            attention_calls=attention_calls,
            exact_scope_calls=exact_calls,
            cleanup_calls=cleanup_calls,
            sequence_rehearsed=state == "REHEARSED",
            private_state_cleared=cleanup_calls == 1,
        )


__all__ = [
    "M85DormantFinalCommandOwner",
    "M85FinalCommandContract",
    "M85FinalCommandSnapshot",
    "M85_FINAL_COMMAND_CONTRACT",
    "M85_FIRST_CONFIRMATION_TEXT",
    "M85_MANUAL_REMOVAL_TEXT",
    "M85_MISSING_REAL_BINDINGS",
    "M85_SECOND_CONFIRMATION_TEXT",
]
