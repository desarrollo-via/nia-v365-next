"""Gated launcher for the current product EAOR.

Preflight performs no construction or I/O.  The execution gate builds only a
two-phase runner and coordinator from deferred factories; owners remain dormant
until the accepted runner begins.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Literal

from .bitrix_event_scoped_r1_control import (
    EVENT_R1_SESSION_TTL_SECONDS,
    EventScopedR1SessionOwner,
)
from .bitrix_event_scoped_r1_gate import (
    EVENT_R1_FIRST_CONFIRMATION,
    EVENT_R1_SECOND_CONFIRMATION,
)
from .bitrix_event_scoped_r1_mount import build_optional_event_scoped_r1_mount
from .bitrix_event_scoped_r1_protected_oauth_builder import (
    build_dormant_real_pre_event_lease_factory,
)
from .r1_key_vault_linux_provisioning_owner import MANIFEST_SHA256
from .r1_key_vault_recovery_resume import recover_and_resume_once
from .r1_pre_event_activation_apply_owner import (
    FIRST_ACTIVATION_CONFIRMATION,
    SECOND_ACTIVATION_CONFIRMATION,
)
from .r1_pre_event_activation_apply_real_binding import (
    ExactAnonymousR1ActivationVerifier,
    build_dormant_real_activation_apply_owner,
)
from .r1_pre_event_activation_preflight import (
    BOT_NEXT_ID,
    BOT_NIA_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DIALOG_ID,
    PROTECTED_SETTING_COUNT,
    PROTECTED_TARGET_ID,
)
from .r1_pre_event_activation_real_binding import R1ActivationDormantRealBinding
from .config import load_settings
from .r1_result_eaor_coordinator import EAOR_ID
from .r1_result_eaor_coordinator import EAOR_ACCEPTANCE
from .r1_result_eaor_product_port import (
    R1EaorActivationOwnerAdapter,
    R1EaorRecoveryResumeAdapter,
    R1EaorSessionOwnerAdapter,
    build_dormant_product_eaor_coordinator,
)
from .r1_result_eaor_product_runner import (
    R1ProductExecutionFactories,
    R1ResultEaorProductRunner,
    build_dormant_product_runner,
)
from .r1_result_eaor_product_real_binding import (
    R1ResultEaorProductRealBinding,
)


INERT_PREFLIGHT_CONFIRMATION = (
    "AUDITAR LANZADOR EAOR R1 SOLO LOCAL SIN EFECTOS"
)
POLL_INTERVAL_SECONDS = 15
OBSERVATION_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class R1ProductLauncherBindings:
    settings_loader: Callable = load_settings
    provisioning_operation: Callable = recover_and_resume_once
    provisioning_adapter: type = R1EaorRecoveryResumeAdapter
    activation_owner_builder: Callable = build_dormant_real_activation_apply_owner
    activation_preflight_binding: type = R1ActivationDormantRealBinding
    activation_verifier: type = ExactAnonymousR1ActivationVerifier
    activation_adapter: type = R1EaorActivationOwnerAdapter
    pre_event_lease_builder: Callable = build_dormant_real_pre_event_lease_factory
    session_owner: type = EventScopedR1SessionOwner
    session_mount_builder: Callable = build_optional_event_scoped_r1_mount
    session_adapter: type = R1EaorSessionOwnerAdapter
    coordinator_builder: Callable = build_dormant_product_eaor_coordinator
    runner_builder: Callable = build_dormant_product_runner
    factory_binding_type: type = R1ResultEaorProductRealBinding


@dataclass(frozen=True)
class R1ProductLauncherPreflight:
    state: Literal[
        "INERT", "READY-EXTERNAL-PREFLIGHT", "READY-CONTRACT-REFRESH",
        "NO-GO-CONFIRMATION", "NO-GO-BINDING-DRIFT",
    ] = "INERT"
    eaor_id: str = EAOR_ID
    evaluated_day: str = ""
    external_envelope_current: bool = False
    exact_bindings_verified: bool = False
    exact_scope_verified: bool = False
    exact_literals_verified: bool = False
    exact_budgets_verified: bool = False
    coordinator_constructions: Literal[0] = 0
    owner_constructions: Literal[0] = 0
    external_calls: Literal[0] = 0
    protected_source_opens: Literal[0] = 0
    secret_reads: Literal[0] = 0
    mutations: Literal[0] = 0
    messages_sent: Literal[0] = 0
    execution_exposed: bool = False


def _bindings_exact(bindings: object) -> bool:
    return bool(
        type(bindings) is R1ProductLauncherBindings
        and bindings.settings_loader is load_settings
        and bindings.provisioning_operation is recover_and_resume_once
        and bindings.provisioning_adapter is R1EaorRecoveryResumeAdapter
        and bindings.activation_owner_builder
        is build_dormant_real_activation_apply_owner
        and bindings.activation_preflight_binding is R1ActivationDormantRealBinding
        and bindings.activation_verifier is ExactAnonymousR1ActivationVerifier
        and bindings.activation_adapter is R1EaorActivationOwnerAdapter
        and bindings.pre_event_lease_builder
        is build_dormant_real_pre_event_lease_factory
        and bindings.session_owner is EventScopedR1SessionOwner
        and bindings.session_mount_builder is build_optional_event_scoped_r1_mount
        and bindings.session_adapter is R1EaorSessionOwnerAdapter
        and bindings.coordinator_builder is build_dormant_product_eaor_coordinator
        and bindings.runner_builder is build_dormant_product_runner
        and bindings.factory_binding_type is R1ResultEaorProductRealBinding
    )


class R1ResultEaorProductLauncher:
    """One-shot pure auditor; productive execution is intentionally absent."""

    __slots__ = ("_bindings", "_current_day", "_used")

    def __init__(
        self,
        *,
        bindings: R1ProductLauncherBindings | None = None,
        current_day: str | None = None,
    ) -> None:
        self._bindings = bindings or R1ProductLauncherBindings()
        self._current_day = current_day or date.today().isoformat()
        self._used = False

    def preflight_once(self, *, confirmation: str) -> R1ProductLauncherPreflight:
        if self._used:
            raise RuntimeError("r1_product_launcher_preflight_reused")
        self._used = True
        if confirmation != INERT_PREFLIGHT_CONFIRMATION:
            return R1ProductLauncherPreflight(
                state="NO-GO-CONFIRMATION", evaluated_day=self._current_day
            )
        bindings_ok = _bindings_exact(self._bindings)
        scope_ok = bool(
            EAOR_ID == "NIA-NEXT-R1-EAOR-INTEGRAL-2026-08-13-V2"
            and MANIFEST_SHA256
            == "16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49"
            and PROTECTED_TARGET_ID == "nia-next/bitrix-r1/protected-settings/v1"
            and PROTECTED_SETTING_COUNT == 7
            and CONTROLLED_CHAT_ID == 78733
            and CONTROLLED_DIALOG_ID == "chat78733"
            and BOT_NEXT_ID == 373259
            and BOT_NIA_ID == 245339
        )
        literals_ok = all(
            type(value) is str and bool(value)
            for value in (
                FIRST_ACTIVATION_CONFIRMATION,
                SECOND_ACTIVATION_CONFIRMATION,
                EVENT_R1_FIRST_CONFIRMATION,
                EVENT_R1_SECOND_CONFIRMATION,
            )
        )
        budgets_ok = bool(
            POLL_INTERVAL_SECONDS == 15
            and OBSERVATION_TIMEOUT_SECONDS == EVENT_R1_SESSION_TTL_SECONDS == 600
        )
        ready = bindings_ok and scope_ok and literals_ok and budgets_ok
        envelope_current = self._current_day == "2026-08-13"
        return R1ProductLauncherPreflight(
            state=(
                "READY-EXTERNAL-PREFLIGHT" if ready and envelope_current
                else "READY-CONTRACT-REFRESH" if ready
                else "NO-GO-BINDING-DRIFT"
            ),
            evaluated_day=self._current_day,
            external_envelope_current=envelope_current,
            exact_bindings_verified=bindings_ok,
            exact_scope_verified=scope_ok,
            exact_literals_verified=literals_ok,
            exact_budgets_verified=budgets_ok,
            execution_exposed=ready and envelope_current,
        )

    def build_runner_once(
        self,
        *,
        acceptance: str,
        factories: R1ProductExecutionFactories,
    ) -> R1ResultEaorProductRunner:
        if self._used:
            raise RuntimeError("r1_product_launcher_reused")
        self._used = True
        if acceptance != EAOR_ACCEPTANCE:
            raise RuntimeError("r1_product_launcher_acceptance_invalid")
        if self._current_day != "2026-08-13":
            raise RuntimeError("r1_product_launcher_contract_expired")
        if not _bindings_exact(self._bindings):
            raise RuntimeError("r1_product_launcher_binding_drift")
        return self._bindings.runner_builder(
            factories=factories,
            acceptance=acceptance,
            coordinator_builder=self._bindings.coordinator_builder,
        )

    def build_runner_from_binding_once(
        self,
        *,
        acceptance: str,
        binding: R1ResultEaorProductRealBinding,
    ) -> R1ResultEaorProductRunner:
        if self._used:
            raise RuntimeError("r1_product_launcher_reused")
        self._used = True
        if acceptance != EAOR_ACCEPTANCE:
            raise RuntimeError("r1_product_launcher_acceptance_invalid")
        if self._current_day != "2026-08-13":
            raise RuntimeError("r1_product_launcher_contract_expired")
        if not _bindings_exact(self._bindings):
            raise RuntimeError("r1_product_launcher_binding_drift")
        if type(binding) is not self._bindings.factory_binding_type:
            raise TypeError("r1_product_launcher_factory_binding_invalid")
        factories = binding.build_plan_once()
        return self._bindings.runner_builder(
            factories=factories,
            acceptance=acceptance,
            coordinator_builder=self._bindings.coordinator_builder,
        )

    def __repr__(self) -> str:
        return "R1ResultEaorProductLauncher(<redacted>)"


def drifted_bindings_for_test(**changes) -> R1ProductLauncherBindings:
    """Test-only helper that keeps production construction closed."""

    return replace(R1ProductLauncherBindings(), **changes)


__all__ = [
    "INERT_PREFLIGHT_CONFIRMATION", "OBSERVATION_TIMEOUT_SECONDS",
    "POLL_INTERVAL_SECONDS", "R1ProductLauncherBindings",
    "R1ProductLauncherPreflight", "R1ResultEaorProductLauncher",
    "drifted_bindings_for_test",
]
