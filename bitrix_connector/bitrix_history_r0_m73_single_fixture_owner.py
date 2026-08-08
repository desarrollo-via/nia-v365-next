"""Owner M73 único para literales, atención fixture y cadena M68-M71."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_dormant_confirmation_coordinator import (
    DormantTwoConfirmationCoordinator,
)
from .bitrix_history_r0_m63_literal_parser import OneShotM63LiteralParser
from .bitrix_history_r0_m68_combined_preflight import CombinedR1PreflightAdapter
from .bitrix_history_r0_m71_rollback_factory_composition import (
    RollbackFactoryCompositionStatus,
    RollbackFactoryM70Composition,
)
from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
    ComposedRoundtripStatus,
)


@dataclass(frozen=True)
class InjectedFixtureAttentionEvidence:
    state: Literal["WAITING-MESSAGE"] = "WAITING-MESSAGE"
    fixture_attention_emitted: bool = True
    fixture_message_signal_received: bool = True
    external_calls: int = 0


FixtureAttentionProbe = Callable[
    [], Awaitable[InjectedFixtureAttentionEvidence]
]
InjectedTextReader = Callable[[], Awaitable[str]]


class _CountingTextReader:
    def __init__(self, reader: InjectedTextReader) -> None:
        self._reader: Optional[InjectedTextReader] = reader
        self.calls = 0

    async def __call__(self) -> str:
        reader = self._reader
        if reader is None:
            raise RuntimeError("m73_text_reader_cleared")
        self.calls += 1
        return await reader()

    def clear(self) -> None:
        self._reader = None


class SingleFixtureOwnerResult(BaseModel):
    """Evidencia pública M73 sin textos, anclas, IDs o respuestas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M73"] = "M73"
    state: Literal["PREPARED", "NO-GO", "CANCELLED"]
    reason: str
    literal_read_calls: int = Field(ge=0, le=3)
    preflight_probe_calls: int = Field(ge=0, le=1)
    attention_probe_calls: int = Field(ge=0, le=1)
    exact_scope_owner_calls: int = Field(ge=0, le=1)
    cleanup_calls: Literal[1] = 1
    fixture_attention_boundary_verified: bool = False
    exact_scope_verified_in_fixtures: bool = False
    exact_scope_verified_in_sealed_memory: bool = False
    exact_scope_rollback_verified: bool = False
    three_logical_links_composed: Literal[True] = True
    formal_real_links_remaining: Literal[4] = 4
    private_state_cleared: Literal[True] = True
    fixture_authorizations_consumed: int = Field(ge=0, le=3)
    real_authorizations_consumed: Literal[False] = False
    first_confirmation_request_ready: Literal[False] = False
    point_8_can_begin: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    human_message_requested: Literal[False] = False
    binding_class: Literal[
        "fixture-double", "sealed-in-memory-concrete"
    ] = "fixture-double"
    fixture_only: bool = True
    concrete_clients_constructed_in_memory: bool = False
    network_capable_resources_accepted: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class SingleFixtureR1Owner:
    """Consume toda la secuencia fixture una vez y limpia todos sus owners."""

    def __init__(
        self,
        *,
        plan: ProtectedRealRoundtripPlan,
        text_reader: InjectedTextReader,
        preflight_adapter: CombinedR1PreflightAdapter,
        attention_probe: FixtureAttentionProbe,
        exact_scope_owner: RollbackFactoryM70Composition,
        timeout_seconds: float = 300.0,
    ) -> None:
        if (
            not isinstance(plan, ProtectedRealRoundtripPlan)
            or not callable(text_reader)
            or not isinstance(preflight_adapter, CombinedR1PreflightAdapter)
            or not callable(attention_probe)
            or not isinstance(exact_scope_owner, RollbackFactoryM70Composition)
            or timeout_seconds <= 0
            or timeout_seconds > 300
        ):
            raise ValueError("m73_single_owner_contract_invalid")
        self._dependencies: Optional[tuple[object, ...]] = (
            plan,
            text_reader,
            preflight_adapter,
            attention_probe,
            exact_scope_owner,
            timeout_seconds,
        )
        self._used = False

    def clear(self) -> None:
        self._dependencies = None

    @property
    def cleared(self) -> bool:
        return self._dependencies is None

    async def run_once(self) -> SingleFixtureOwnerResult:
        if self._used or self._dependencies is None:
            self.clear()
            return SingleFixtureOwnerResult(
                state="NO-GO",
                reason="m73_single_owner_reuse_rejected",
                literal_read_calls=0,
                preflight_probe_calls=0,
                attention_probe_calls=0,
                exact_scope_owner_calls=0,
                fixture_authorizations_consumed=0,
            )
        self._used = True
        dependencies, self._dependencies = self._dependencies, None
        counting_reader: Optional[_CountingTextReader] = None
        parser: Optional[OneShotM63LiteralParser] = None
        preflight_calls = 0
        attention_calls = 0
        exact_calls = 0
        attention_verified = False
        exact_verified = False
        rollback_verified = False
        binding_class = "fixture-double"
        try:
            (
                plan,
                text_reader,
                preflight_adapter,
                attention_probe,
                exact_scope_owner,
                timeout_seconds,
            ) = dependencies
            counting_reader = _CountingTextReader(text_reader)
            parser = OneShotM63LiteralParser(text_reader=counting_reader)

            async def preflight():
                nonlocal preflight_calls
                preflight_calls = 1
                return await preflight_adapter.probe_once()

            async def exact_scope():
                nonlocal attention_calls, exact_calls
                nonlocal attention_verified, exact_verified
                nonlocal rollback_verified, binding_class
                attention_calls = 1
                evidence = await attention_probe()
                if (
                    type(evidence) is not InjectedFixtureAttentionEvidence
                    or evidence.state != "WAITING-MESSAGE"
                    or evidence.fixture_attention_emitted is not True
                    or evidence.fixture_message_signal_received is not True
                    or evidence.external_calls != 0
                ):
                    raise ValueError("m73_fixture_attention_invalid")
                attention_verified = True
                exact_calls = 1
                exact = await exact_scope_owner.run_once()
                binding_class = exact.binding_class
                if exact.status is RollbackFactoryCompositionStatus.VERIFIED:
                    exact_verified = True
                    return ComposedRoundtripResult(
                        status=ComposedRoundtripStatus.VERIFIED,
                        reason="composed_roundtrip_verified_and_preserved",
                        post_send_history_read_count=1,
                        rollback_call_count=0,
                        delete_call_count=0,
                        post_delete_history_read_count=0,
                        exact_send_receipt_obtained=True,
                        exact_send_receipt_used_for_verification=True,
                        fixture_reply_present_same_session=True,
                        fixture_reply_preserved=True,
                        binding_class=exact.binding_class,
                        fixture_only=exact.fixture_only,
                        concrete_clients_constructed_in_memory=(
                            exact.concrete_clients_constructed_in_memory
                        ),
                    )
                if exact.status is RollbackFactoryCompositionStatus.ROLLED_BACK:
                    exact_verified = True
                    rollback_verified = True
                    return ComposedRoundtripResult(
                        status=ComposedRoundtripStatus.VERIFIED,
                        reason="composed_sealed_rollback_safety_verified",
                        post_send_history_read_count=1,
                        rollback_call_count=1,
                        delete_call_count=1,
                        post_delete_history_read_count=1,
                        exact_send_receipt_obtained=True,
                        exact_send_receipt_used_for_verification=True,
                        exact_send_receipt_used_for_rollback=True,
                        fixture_rollback_verified=True,
                        rollback_required_after_receipt_failure=True,
                        binding_class=exact.binding_class,
                        fixture_only=exact.fixture_only,
                        concrete_clients_constructed_in_memory=(
                            exact.concrete_clients_constructed_in_memory
                        ),
                    )
                return ComposedRoundtripResult(
                    status=ComposedRoundtripStatus.NO_GO,
                    reason="composed_roundtrip_stopped_before_receipt",
                    post_send_history_read_count=0,
                    rollback_call_count=0,
                    delete_call_count=0,
                    post_delete_history_read_count=0,
                )

            coordinator = DormantTwoConfirmationCoordinator(
                plan=plan,
                first_confirmation_reader=parser.read_first_confirmation,
                preflight_probe=preflight,
                manual_evidence_reader=parser.read_manual_evidence,
                second_confirmation_reader=parser.read_second_confirmation,
                exact_scope_probe=exact_scope,
                timeout_seconds=timeout_seconds,
            )
            snapshot = await coordinator.run_once()
            return SingleFixtureOwnerResult(
                state=snapshot.state,
                reason=snapshot.reason,
                literal_read_calls=counting_reader.calls,
                preflight_probe_calls=preflight_calls,
                attention_probe_calls=attention_calls,
                exact_scope_owner_calls=exact_calls,
                fixture_attention_boundary_verified=attention_verified,
                exact_scope_verified_in_fixtures=(
                    exact_verified and binding_class == "fixture-double"
                ),
                exact_scope_verified_in_sealed_memory=(
                    exact_verified
                    and binding_class == "sealed-in-memory-concrete"
                ),
                exact_scope_rollback_verified=rollback_verified,
                fixture_authorizations_consumed=counting_reader.calls,
                binding_class=binding_class,
                fixture_only=binding_class == "fixture-double",
                concrete_clients_constructed_in_memory=(
                    binding_class == "sealed-in-memory-concrete"
                ),
            )
        finally:
            if parser is not None:
                parser.clear()
            if counting_reader is not None:
                counting_reader.clear()
            if "preflight_adapter" in locals():
                preflight_adapter.clear()
            if "exact_scope_owner" in locals():
                exact_scope_owner.clear()
            dependencies = ()
            self.clear()


__all__ = [
    "FixtureAttentionProbe",
    "InjectedFixtureAttentionEvidence",
    "SingleFixtureOwnerResult",
    "SingleFixtureR1Owner",
]
