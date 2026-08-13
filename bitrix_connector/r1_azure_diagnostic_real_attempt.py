"""Inert construction and sanitized real-binding adapter for R1 Azure diagnosis."""

from __future__ import annotations

from collections.abc import Callable

from .r1_azure_diagnostic_coordinator import (
    MAX_HEALTH_PAIRS_PER_ATTEMPT,
    MAX_READS_PER_ATTEMPT,
    R1AzureDiagnosticAttemptResult,
    R1AzureDiagnosticCoordinator,
)
from .r1_key_vault_linux_provisioning_real_binding import (
    AzureCliExactProvisioningControl,
    ExactAzureCliCommandRunner,
    ExactDormantHealthReader,
)


class _CountingRunner:
    __slots__ = ("calls", "_inner")

    def __init__(self, inner: object) -> None:
        if (
            not callable(getattr(inner, "run_exact_once", None))
            or not callable(getattr(inner, "close", None))
        ):
            raise TypeError("r1_azure_diagnostic_runner_invalid")
        self._inner = inner
        self.calls = 0

    async def run_exact_once(self, command):
        if self.calls >= MAX_READS_PER_ATTEMPT:
            raise RuntimeError("r1_azure_diagnostic_read_budget_exhausted")
        self.calls += 1
        return await self._inner.run_exact_once(command)

    async def close(self) -> None:
        await self._inner.close()


class _CountingHealth:
    __slots__ = ("calls", "_inner")

    def __init__(self, inner: object) -> None:
        if (
            not callable(getattr(inner, "read_exact_once", None))
            or not callable(getattr(inner, "close", None))
        ):
            raise TypeError("r1_azure_diagnostic_health_invalid")
        self._inner = inner
        self.calls = 0

    async def read_exact_once(self) -> bool:
        if self.calls >= MAX_HEALTH_PAIRS_PER_ATTEMPT:
            raise RuntimeError("r1_azure_diagnostic_health_budget_exhausted")
        self.calls += 1
        return await self._inner.read_exact_once()

    async def close(self) -> None:
        await self._inner.close()


def _category(error: BaseException) -> tuple[str, str]:
    code = str(error)
    if code == "r1_kv_binding_command_failed_authentication":
        return "AUTHENTICATION-REQUIRED", "authentication"
    if code == "r1_kv_binding_command_failed_transport":
        return "NO-GO-RECOVERABLE", "transport"
    if code == "r1_kv_binding_command_failed_unknown":
        return "NO-GO-RECOVERABLE", "unknown"
    if code == "r1_kv_binding_command_failed_authorization":
        return "NO-GO-TERMINAL", "authorization"
    if code == "r1_kv_binding_command_failed_not_found":
        return "NO-GO-TERMINAL", "not_found"
    if "drift" in code:
        return "NO-GO-TERMINAL", "drift"
    return "NO-GO-TERMINAL", "invalid_evidence"


class R1AzureDiagnosticRealAttempt:
    """Adapts one exact provisioning preflight without opening protected sources."""

    __slots__ = ("_control", "_health", "_runner", "_used")

    def __init__(
        self,
        *,
        control: AzureCliExactProvisioningControl,
        runner: _CountingRunner,
        health: _CountingHealth,
    ) -> None:
        self._control = control
        self._runner = runner
        self._health = health
        self._used = False

    async def run_once(self) -> R1AzureDiagnosticAttemptResult:
        if self._used:
            raise RuntimeError("r1_azure_diagnostic_real_attempt_reused")
        self._used = True
        try:
            await self._control.preflight_exact_once()
        except BaseException as error:
            state, category = _category(error)
            return R1AzureDiagnosticAttemptResult(
                state=state,
                category=category,
                read_calls=self._runner.calls,
                health_pairs=self._health.calls,
            )
        return R1AzureDiagnosticAttemptResult(
            state="GO",
            category="none",
            read_calls=self._runner.calls,
            health_pairs=self._health.calls,
        )

    async def close(self) -> None:
        await self._control.close()


def build_real_r1_azure_diagnostic_coordinator(
    *,
    local_state_guard: Callable[[], bool],
    max_attempts: int = 3,
    runner_factory: Callable[[], object] = ExactAzureCliCommandRunner,
    health_factory: Callable[[], object] = ExactDormantHealthReader,
) -> R1AzureDiagnosticCoordinator:
    """Builds an inert coordinator; effects begin only when ``run_once`` is awaited."""

    if not callable(local_state_guard):
        raise TypeError("r1_azure_diagnostic_local_state_guard_invalid")

    def attempt_factory(_attempt_number: int) -> R1AzureDiagnosticRealAttempt:
        runner = _CountingRunner(runner_factory())
        health = _CountingHealth(health_factory())
        control = AzureCliExactProvisioningControl(
            runner=runner,
            health=health,
            local_state_guard=local_state_guard,
            setting_absent=True,
        )
        return R1AzureDiagnosticRealAttempt(
            control=control,
            runner=runner,
            health=health,
        )

    return R1AzureDiagnosticCoordinator(
        attempt_factory=attempt_factory,
        max_attempts=max_attempts,
    )


__all__ = [
    "R1AzureDiagnosticRealAttempt",
    "build_real_r1_azure_diagnostic_coordinator",
]
