"""Coordinador M65 dormido de dos confirmaciones, sólo para dobles."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
    ComposedRoundtripStatus,
)


FIRST_CONFIRMATION_SCOPE = "r1-first-preflight-and-preparation-exact"
SECOND_CONFIRMATION_SCOPE = "r1-second-immediate-execution-exact"
MANUAL_REMOVAL_SCOPE = "r1-production-bot-manually-removed"


@dataclass(frozen=True)
class InjectedConfirmation:
    approved: bool
    scope: str


@dataclass(frozen=True)
class InjectedFreshPreflightEvidence:
    state: str = "READY"
    chat_id: int = 78733
    dialog_id: str = "chat78733"
    controlled_bot_id: int = 373259
    resources_closed: bool = True
    drift_detected: bool = False
    external_calls: int = 0


@dataclass(frozen=True)
class InjectedManualRemovalEvidence:
    confirmed: bool
    scope: str
    production_bot_id: int = 245339


@dataclass(frozen=True)
class DormantConfirmationSnapshot:
    phase: Literal["M65"] = "M65"
    state: Literal["PREPARED", "NO-GO", "CANCELLED"] = "NO-GO"
    reason: str = "dormant_confirmation_coordinator_not_started"
    first_confirmation_calls: int = 0
    preflight_probe_calls: int = 0
    manual_evidence_calls: int = 0
    second_confirmation_calls: int = 0
    exact_scope_probe_calls: int = 0
    cleanup_calls: int = 0
    first_confirmation_verified: bool = False
    preflight_verified: bool = False
    manual_removal_verified: bool = False
    second_confirmation_verified: bool = False
    exact_scope_verified_in_doubles: bool = False
    private_state_cleared: bool = False
    m63_drafts_consumed: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    cli_available: Literal[False] = False
    human_message_requested: Literal[False] = False
    real_execution_enabled: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


ConfirmationReader = Callable[[], Awaitable[InjectedConfirmation]]
PreflightProbe = Callable[[], Awaitable[InjectedFreshPreflightEvidence]]
ManualEvidenceReader = Callable[[], Awaitable[InjectedManualRemovalEvidence]]
ExactScopeProbe = Callable[[], Awaitable[ComposedRoundtripResult]]


class DormantTwoConfirmationCoordinator:
    """Consume una sola secuencia ficticia y elimina todas sus dependencias."""

    def __init__(
        self,
        *,
        plan: ProtectedRealRoundtripPlan,
        first_confirmation_reader: ConfirmationReader,
        preflight_probe: PreflightProbe,
        manual_evidence_reader: ManualEvidenceReader,
        second_confirmation_reader: ConfirmationReader,
        exact_scope_probe: ExactScopeProbe,
        timeout_seconds: float = 300.0,
    ) -> None:
        dependencies = (
            first_confirmation_reader,
            preflight_probe,
            manual_evidence_reader,
            second_confirmation_reader,
            exact_scope_probe,
        )
        if (
            not isinstance(plan, ProtectedRealRoundtripPlan)
            or plan.state != "NO-GO"
            or plan.reconciled_phase != "M64"
            or plan.m63_confirmation_drafts_consumable
            or plan.real_execution_authorized
            or not all(callable(item) for item in dependencies)
            or timeout_seconds <= 0
            or timeout_seconds > 300
        ):
            raise ValueError("dormant_confirmation_contract_invalid")
        self._plan: Optional[ProtectedRealRoundtripPlan] = plan
        self._dependencies: Optional[tuple[Callable[[], Awaitable[object]], ...]] = (
            dependencies
        )
        self._timeout_seconds = timeout_seconds
        self._used = False

    async def run_once(self) -> DormantConfirmationSnapshot:
        if self._used:
            return DormantConfirmationSnapshot(
                reason="dormant_confirmation_reuse_rejected",
                private_state_cleared=self._dependencies is None,
            )
        self._used = True
        calls = [0, 0, 0, 0, 0]
        verified = [False, False, False, False, False]
        reason = "dormant_confirmation_failed_safe"
        state: Literal["PREPARED", "NO-GO", "CANCELLED"] = "NO-GO"
        try:
            dependencies = self._dependencies
            if dependencies is None:
                raise RuntimeError("dormant_confirmation_dependencies_cleared")
            async with asyncio.timeout(self._timeout_seconds):
                calls[0] = 1
                first = await dependencies[0]()
                if (
                    type(first) is not InjectedConfirmation
                    or first.approved is not True
                    or first.scope != FIRST_CONFIRMATION_SCOPE
                ):
                    reason = "dormant_first_confirmation_rejected"
                    raise ValueError(reason)
                verified[0] = True

                calls[1] = 1
                preflight = await dependencies[1]()
                if (
                    type(preflight) is not InjectedFreshPreflightEvidence
                    or preflight.state != "READY"
                    or preflight.chat_id != 78733
                    or preflight.dialog_id != "chat78733"
                    or preflight.controlled_bot_id != 373259
                    or preflight.resources_closed is not True
                    or preflight.drift_detected is not False
                    or preflight.external_calls != 0
                ):
                    reason = "dormant_preflight_drift_rejected"
                    raise ValueError(reason)
                verified[1] = True

                calls[2] = 1
                manual = await dependencies[2]()
                if (
                    type(manual) is not InjectedManualRemovalEvidence
                    or manual.confirmed is not True
                    or manual.scope != MANUAL_REMOVAL_SCOPE
                    or manual.production_bot_id != 245339
                ):
                    reason = "dormant_manual_evidence_rejected"
                    raise ValueError(reason)
                verified[2] = True

                calls[3] = 1
                second = await dependencies[3]()
                if (
                    type(second) is not InjectedConfirmation
                    or second.approved is not True
                    or second.scope != SECOND_CONFIRMATION_SCOPE
                ):
                    reason = "dormant_second_confirmation_rejected"
                    raise ValueError(reason)
                verified[3] = True

                calls[4] = 1
                exact = await dependencies[4]()
                if (
                    type(exact) is not ComposedRoundtripResult
                    or exact.status is not ComposedRoundtripStatus.VERIFIED
                    or exact.binding_class not in {
                        "fixture-double",
                        "sealed-in-memory-concrete",
                    }
                    or exact.network_capable_resources_accepted
                    or exact.external_calls != 0
                    or exact.real_execution_authorized
                    or exact.nia_next_called
                    or exact.bitrix_written
                ):
                    reason = "dormant_exact_scope_probe_rejected"
                    raise ValueError(reason)
                verified[4] = True
                state = "PREPARED"
                reason = "dormant_two_confirmation_path_verified_in_doubles"
        except asyncio.TimeoutError:
            reason = "dormant_confirmation_timeout_terminal"
        except asyncio.CancelledError:
            state = "CANCELLED"
            reason = "dormant_confirmation_cancelled_terminal"
        except BaseException:
            pass
        finally:
            self._plan = None
            self._dependencies = None

        return DormantConfirmationSnapshot(
            state=state,
            reason=reason,
            first_confirmation_calls=calls[0],
            preflight_probe_calls=calls[1],
            manual_evidence_calls=calls[2],
            second_confirmation_calls=calls[3],
            exact_scope_probe_calls=calls[4],
            cleanup_calls=1,
            first_confirmation_verified=verified[0],
            preflight_verified=verified[1],
            manual_removal_verified=verified[2],
            second_confirmation_verified=verified[3],
            exact_scope_verified_in_doubles=verified[4],
            private_state_cleared=True,
        )


__all__ = [
    "DormantConfirmationSnapshot",
    "DormantTwoConfirmationCoordinator",
    "FIRST_CONFIRMATION_SCOPE",
    "InjectedConfirmation",
    "InjectedFreshPreflightEvidence",
    "InjectedManualRemovalEvidence",
    "MANUAL_REMOVAL_SCOPE",
    "SECOND_CONFIRMATION_SCOPE",
]
