"""Dormant real binding for the exact product EAOR factory plan.

The binding captures only deferred capabilities.  Building it or its plan does
not load settings, open protected sources, construct owners, perform I/O, or
mutate any external surface.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
from typing import Callable, Literal

from .r1_key_vault_recovery_resume import recover_and_resume_once
from .r1_pre_event_activation_apply_real_binding import (
    ExactActivationAzureCliRunner,
    ExactAnonymousR1ActivationVerifier,
    build_dormant_real_activation_apply_owner,
)
from .r1_result_eaor_activation_adapter import R1EaorActivationOwnerAdapter
from .r1_result_eaor_product_port import (
    R1EaorRecoveryResumeAdapter,
)
from .r1_result_eaor_remote_session_adapter import R1EaorRemoteSessionAdapter
from .r1_result_eaor_product_runner import R1ProductExecutionFactories


@dataclass(frozen=True)
class R1ProductFactoryRuntime:
    local_state_guard: Callable[[], bool]
    activation_preflight_supplier: Callable
    remote_session_client_builder: Callable
    provisioning_operation: Callable | None = None
    provisioning_runner: object | None = None
    provisioning_health: object | None = None
    provisioning_source_builder: Callable | None = None
    provisioning_sink: object | None = None
    activation_verifier_builder: Callable = ExactAnonymousR1ActivationVerifier
    activation_runner_factory: Callable = ExactActivationAzureCliRunner
    runtime_finalizer: Callable | None = None

    def __post_init__(self) -> None:
        if not all(callable(item) for item in (
            self.local_state_guard,
            self.activation_preflight_supplier,
            self.remote_session_client_builder,
            self.activation_verifier_builder,
            self.activation_runner_factory,
        )):
            raise TypeError("r1_product_factory_runtime_invalid")
        if self.provisioning_operation is not None and not callable(
            self.provisioning_operation
        ):
            raise TypeError("r1_product_factory_runtime_invalid")
        if self.runtime_finalizer is not None and not callable(
            self.runtime_finalizer
        ):
            raise TypeError("r1_product_factory_runtime_invalid")


@dataclass(frozen=True)
class R1ProductFactoryBindingDependencies:
    provisioning_operation: Callable = recover_and_resume_once
    provisioning_adapter: type = R1EaorRecoveryResumeAdapter
    activation_owner_builder: Callable = build_dormant_real_activation_apply_owner
    activation_adapter: type = R1EaorActivationOwnerAdapter
    session_adapter: type = R1EaorRemoteSessionAdapter


def _dependencies_exact(item: object) -> bool:
    return bool(
        type(item) is R1ProductFactoryBindingDependencies
        and item.provisioning_operation is recover_and_resume_once
        and item.provisioning_adapter is R1EaorRecoveryResumeAdapter
        and item.activation_owner_builder is build_dormant_real_activation_apply_owner
        and item.activation_adapter is R1EaorActivationOwnerAdapter
        and item.session_adapter is R1EaorRemoteSessionAdapter
    )


@dataclass(frozen=True)
class R1ProductFactoryBindingPreview:
    state: Literal["BOUND-DORMANT", "NO-GO-BINDING-DRIFT"]
    dependencies_exact: bool
    plan_constructions: int = 0
    factory_calls: Literal[0] = 0
    settings_loads: Literal[0] = 0
    protected_source_opens: Literal[0] = 0
    external_calls: Literal[0] = 0
    mutations: Literal[0] = 0
    messages_sent: Literal[0] = 0


class R1ResultEaorProductRealBinding:
    """One-shot producer of deferred, structurally exact product factories."""

    __slots__ = ("_dependencies", "_runtime", "_used")

    def __init__(
        self,
        *,
        runtime: R1ProductFactoryRuntime,
        dependencies: R1ProductFactoryBindingDependencies | None = None,
    ) -> None:
        if type(runtime) is not R1ProductFactoryRuntime:
            raise TypeError("r1_product_factory_runtime_invalid")
        self._runtime = runtime
        self._dependencies = dependencies or R1ProductFactoryBindingDependencies()
        self._used = False

    def preview(self) -> R1ProductFactoryBindingPreview:
        exact = _dependencies_exact(self._dependencies)
        return R1ProductFactoryBindingPreview(
            state="BOUND-DORMANT" if exact else "NO-GO-BINDING-DRIFT",
            dependencies_exact=exact,
        )

    def build_plan_once(self) -> R1ProductExecutionFactories:
        runtime, self._runtime = self._runtime, None
        dependencies, self._dependencies = self._dependencies, None
        if (
            self._used
            or runtime is None
            or not _dependencies_exact(dependencies)
        ):
            self._used = True
            raise RuntimeError("r1_product_factory_binding_reused_or_drifted")
        self._used = True

        def provision():
            kwargs = {"local_state_guard": runtime.local_state_guard}
            if runtime.provisioning_runner is not None:
                kwargs["runner"] = runtime.provisioning_runner
            if runtime.provisioning_health is not None:
                kwargs["health"] = runtime.provisioning_health
            if runtime.provisioning_source_builder is not None:
                kwargs["source_builder"] = runtime.provisioning_source_builder
            if runtime.provisioning_sink is not None:
                kwargs["sink"] = runtime.provisioning_sink
            return dependencies.provisioning_adapter(
                operation=(
                    runtime.provisioning_operation
                    or dependencies.provisioning_operation
                ),
                **kwargs,
            )

        def activate():
            verifier = runtime.activation_verifier_builder()
            owner = dependencies.activation_owner_builder(
                verifier=verifier,
                runner_factory=runtime.activation_runner_factory,
            )
            return dependencies.activation_adapter(
                owner=owner,
                preflight_supplier=runtime.activation_preflight_supplier,
            )

        def session():
            client = runtime.remote_session_client_builder()
            if inspect.isawaitable(client):
                async def build_async():
                    return dependencies.session_adapter(client=await client)
                return build_async()
            return dependencies.session_adapter(client=client)

        return R1ProductExecutionFactories(
            provisioning_factory=provision,
            activation_factory=activate,
            session_factory=session,
            runtime_finalizer=runtime.runtime_finalizer,
        )

    def __repr__(self) -> str:
        return "R1ResultEaorProductRealBinding(<redacted>)"


def build_dormant_real_product_factory_binding(
    *,
    local_state_guard: Callable[[], bool],
    activation_preflight_supplier: Callable,
    remote_session_client_builder: Callable,
) -> R1ResultEaorProductRealBinding:
    return R1ResultEaorProductRealBinding(
        runtime=R1ProductFactoryRuntime(
            local_state_guard=local_state_guard,
            activation_preflight_supplier=activation_preflight_supplier,
            remote_session_client_builder=remote_session_client_builder,
        )
    )


def drifted_product_factory_dependencies_for_test(
    **changes,
) -> R1ProductFactoryBindingDependencies:
    return replace(R1ProductFactoryBindingDependencies(), **changes)


__all__ = [
    "R1ProductFactoryBindingDependencies",
    "R1ProductFactoryBindingPreview",
    "R1ProductFactoryRuntime",
    "R1ResultEaorProductRealBinding",
    "build_dormant_real_product_factory_binding",
    "drifted_product_factory_dependencies_for_test",
]
