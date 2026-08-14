"""Inert unified EAOR port over the exact provisioning, activation and session owners."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable

from .bitrix_event_scoped_r1_control import EventScopedR1SessionOwner
from .bitrix_event_scoped_r1_gate import (
    EVENT_R1_FIRST_CONFIRMATION,
    EVENT_R1_SECOND_CONFIRMATION,
)
from .r1_key_vault_linux_provisioning_owner import (
    FIRST_CONFIRMATION_TEXT,
    SECOND_CONFIRMATION_TEXT,
    R1KeyVaultLinuxProvisioningOwner,
)
from .r1_result_eaor_activation_adapter import R1EaorActivationOwnerAdapter
from .r1_result_eaor_coordinator import R1EaorStageResult, R1ResultEaorCoordinator
from .r1_result_eaor_remote_session_adapter import R1EaorRemoteSessionAdapter
from .r1_key_vault_recovery_resume import (
    RecoveryResumeResult,
    recover_and_resume_once,
)


class R1EaorProvisioningOwnerAdapter:
    __slots__ = ("_owner", "_used")

    def __init__(self, *, owner: R1KeyVaultLinuxProvisioningOwner) -> None:
        if type(owner) is not R1KeyVaultLinuxProvisioningOwner:
            raise TypeError("r1_eaor_provisioning_owner_invalid")
        self._owner = owner
        self._used = False

    async def provision_once(self) -> R1EaorStageResult:
        if self._used:
            raise RuntimeError("r1_eaor_provisioning_adapter_reused")
        self._used = True
        prepared = await self._owner.prepare_once(
            first_confirmation=FIRST_CONFIRMATION_TEXT
        )
        if prepared.state != "AWAITING-SECOND-CONFIRMATION":
            return R1EaorStageResult(
                "NO-GO-REMAINDER", resources_closed=prepared.resources_closed
            )
        result = await self._owner.execute_once(
            second_confirmation=SECOND_CONFIRMATION_TEXT
        )
        if result.state == "PROVISIONED-DORMANT-VERIFIED":
            return R1EaorStageResult(
                "PROVISIONED-DORMANT-VERIFIED",
                resources_closed=result.resources_closed,
            )
        state = (
            "FAILED-RESTORED"
            if result.state == "FAILED-RESTORED"
            else "NO-GO-REMAINDER"
        )
        return R1EaorStageResult(state, resources_closed=result.resources_closed)


class R1EaorRecoveryResumeAdapter:
    """EAOR adapter for the resumable v2 Key Vault checkpoint owner."""

    __slots__ = ("_operation", "_kwargs", "_used")

    def __init__(self, *, operation=recover_and_resume_once, **kwargs) -> None:
        if not callable(operation):
            raise TypeError("r1_eaor_recovery_operation_invalid")
        self._operation = operation
        self._kwargs = dict(kwargs)
        self._used = False

    async def provision_once(self) -> R1EaorStageResult:
        operation, self._operation = self._operation, None
        kwargs, self._kwargs = self._kwargs, {}
        if self._used or operation is None:
            self._used = True
            raise RuntimeError("r1_eaor_recovery_adapter_reused")
        self._used = True
        result = await operation(**kwargs)
        if type(result) is not RecoveryResumeResult:
            raise TypeError("r1_eaor_recovery_result_invalid")
        mapping = {
            "RECOVERED-DORMANT-VERIFIED": "PROVISIONED-DORMANT-VERIFIED",
            "WAITING-DATA-PLANE-SAFE": "WAITING-DATA-PLANE-SAFE",
            "WAITING-SECRET-ACCESS-SAFE": "WAITING-SECRET-ACCESS-SAFE",
            "ATTENTION-REQUIRED-AUTHENTICATION-SAFE": (
                "ATTENTION-REQUIRED-AUTHENTICATION-SAFE"
            ),
            "FAILED-RESTORED": "FAILED-RESTORED",
            "NO-GO-REMAINDER": "NO-GO-REMAINDER",
        }
        return R1EaorStageResult(
            mapping.get(result.state, "NO-GO-REMAINDER"),
            resources_closed=result.resources_closed,
            failure_stage=result.failure_stage,
            failure_category=result.failure_category,
        )


class R1EaorSessionOwnerAdapter:
    __slots__ = (
        "_armed", "_clock", "_closed", "_observed", "_owner",
        "_poll_interval", "_sleeper", "_timeout",
    )

    def __init__(
        self,
        *,
        owner: EventScopedR1SessionOwner,
        poll_interval_seconds: int = 15,
        observation_timeout_seconds: int = 600,
        clock: Callable[[], float] = time.monotonic,
        sleeper=asyncio.sleep,
    ) -> None:
        if (
            type(owner) is not EventScopedR1SessionOwner
            or type(poll_interval_seconds) is not int
            or not 15 <= poll_interval_seconds <= 30
            or type(observation_timeout_seconds) is not int
            or not 60 <= observation_timeout_seconds <= 600
            or not callable(clock)
            or not callable(sleeper)
        ):
            raise TypeError("r1_eaor_session_owner_invalid")
        self._owner = owner
        self._poll_interval = poll_interval_seconds
        self._timeout = observation_timeout_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._armed = False
        self._observed = False
        self._closed = False

    async def arm_once(self) -> R1EaorStageResult:
        if self._armed or self._closed:
            raise RuntimeError("r1_eaor_session_adapter_reused")
        first = await self._owner.accept_first_confirmation_once(
            EVENT_R1_FIRST_CONFIRMATION
        )
        if first.state != "AWAITING-SECOND-CONFIRMATION":
            return R1EaorStageResult("NO-GO-REMAINDER")
        second = await self._owner.accept_second_confirmation_once(
            EVENT_R1_SECOND_CONFIRMATION
        )
        exact = (
            second.state == "ATTENTION-REQUIRED"
            and second.attention_required_now
            and second.human_message_required_now
            and second.pre_event_lease_bound
            and second.pre_event_lease_state == "AWAITING-EVENT"
            and second.participant_arm_attempts == 1
            and second.human_message_authorizations == 1
        )
        if not exact:
            await self.close()
            return R1EaorStageResult("NO-GO-REMAINDER")
        self._armed = True
        return R1EaorStageResult("ATTENTION-REQUIRED")

    async def observe_after_human_once(self) -> R1EaorStageResult:
        if not self._armed or self._observed or self._closed:
            raise RuntimeError("r1_eaor_session_adapter_not_armed")
        self._observed = True
        deadline = self._clock() + self._timeout
        while True:
            snapshot = await self._owner.snapshot()
            restored = (
                snapshot.pre_event_lease_state in {"RESTORED", "EXPIRED-RESTORED"}
                and snapshot.participant_rollback_attempts == 1
                and snapshot.participant_rollback_verified
            )
            if snapshot.state == "VERIFIED" and restored:
                return R1EaorStageResult("VERIFIED-RESTORED")
            if snapshot.state == "EXPIRED" and restored:
                return R1EaorStageResult("EXPIRED-RESTORED")
            if snapshot.state in {"ROLLED-BACK", "NO-GO", "DISARMED"}:
                return R1EaorStageResult(
                    "FAILED-RESTORED" if restored else "NO-GO-REMAINDER",
                    resources_closed=restored,
                )
            if self._clock() >= deadline:
                await self.close()
                return R1EaorStageResult("EXPIRED-RESTORED")
            await self._sleeper(self._poll_interval)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        snapshot = await self._owner.snapshot()
        if snapshot.state in {
            "AWAITING-SECOND-CONFIRMATION", "ATTENTION-REQUIRED"
        }:
            result = await self._owner.disarm_once()
            if result.state != "DISARMED" or (
                result.pre_event_lease_bound
                and not result.participant_rollback_verified
            ):
                raise RuntimeError("r1_eaor_session_close_remainder")


class R1ResultEaorProductPort:
    """Lazily constructs each product owner only when its EAOR stage begins."""

    __slots__ = (
        "_activation", "_activation_factory", "_closed", "_provisioning_factory",
        "_session", "_session_factory", "_used",
    )

    def __init__(
        self,
        *,
        provisioning_factory: Callable[[], object],
        activation_factory: Callable[[], R1EaorActivationOwnerAdapter],
        session_factory: Callable[[], object],
    ) -> None:
        if not all(callable(item) for item in (
            provisioning_factory, activation_factory, session_factory
        )):
            raise TypeError("r1_eaor_product_port_factory_invalid")
        self._provisioning_factory = provisioning_factory
        self._activation_factory = activation_factory
        self._session_factory = session_factory
        self._activation = None
        self._session = None
        self._used: set[str] = set()
        self._closed = False

    def _claim(self, stage: str) -> None:
        if self._closed or stage in self._used:
            raise RuntimeError("r1_eaor_product_port_stage_reused")
        self._used.add(stage)

    async def provision_once(self) -> R1EaorStageResult:
        self._claim("provision")
        factory, self._provisioning_factory = self._provisioning_factory, None
        adapter = factory() if factory is not None else None
        if type(adapter) not in {
            R1EaorProvisioningOwnerAdapter, R1EaorRecoveryResumeAdapter
        }:
            raise TypeError("r1_eaor_provisioning_adapter_invalid")
        return await adapter.provision_once()

    async def activate_once(self) -> R1EaorStageResult:
        self._claim("activate")
        factory, self._activation_factory = self._activation_factory, None
        adapter = factory() if factory is not None else None
        if inspect.isawaitable(adapter):
            adapter = await adapter
        if type(adapter) is not R1EaorActivationOwnerAdapter:
            raise TypeError("r1_eaor_activation_adapter_invalid")
        self._activation = adapter
        return await adapter.activate_once()

    async def arm_session_once(self) -> R1EaorStageResult:
        self._claim("arm")
        factory, self._session_factory = self._session_factory, None
        adapter = factory() if factory is not None else None
        if inspect.isawaitable(adapter):
            adapter = await adapter
        if type(adapter) not in {
            R1EaorSessionOwnerAdapter, R1EaorRemoteSessionAdapter
        }:
            raise TypeError("r1_eaor_session_adapter_invalid")
        self._session = adapter
        return await adapter.arm_once()

    async def observe_after_human_once(self) -> R1EaorStageResult:
        self._claim("observe")
        if self._session is None:
            raise RuntimeError("r1_eaor_session_adapter_unavailable")
        return await self._session.observe_after_human_once()

    async def restore_activation_once(self) -> R1EaorStageResult:
        self._claim("restore_activation")
        if self._activation is None:
            raise RuntimeError("r1_eaor_activation_adapter_unavailable")
        return await self._activation.restore_once()

    async def abort_waiting_once(self) -> R1EaorStageResult:
        """Restore the armed participant/session before restoring activation."""

        self._claim("abort_waiting")
        session, self._session = self._session, None
        activation, self._activation = self._activation, None
        if session is None or activation is None:
            raise RuntimeError("r1_eaor_abort_dependencies_unavailable")
        session_restored = False
        activation_result = None
        try:
            await session.close()
            session_restored = True
        except BaseException:
            session_restored = False
        try:
            activation_result = await activation.restore_once()
        except BaseException:
            activation_result = None
        finally:
            self._closed = True
            self._provisioning_factory = None
            self._activation_factory = None
            self._session_factory = None
        exact = bool(
            session_restored
            and type(activation_result) is R1EaorStageResult
            and activation_result.state == "VERIFIED-RESTORED"
            and activation_result.resources_closed
        )
        return R1EaorStageResult(
            "VERIFIED-RESTORED" if exact else "NO-GO-REMAINDER",
            resources_closed=exact,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        session, self._session = self._session, None
        self._provisioning_factory = None
        self._activation_factory = None
        self._session_factory = None
        if session is not None:
            await session.close()

    def __repr__(self) -> str:
        return "R1ResultEaorProductPort(<redacted>)"


def build_dormant_product_eaor_coordinator(
    *,
    provisioning_factory: Callable[[], object],
    activation_factory: Callable[[], R1EaorActivationOwnerAdapter],
    session_factory: Callable[[], object],
) -> R1ResultEaorCoordinator:
    """Composes the whole product lifecycle; construction invokes no factory."""

    return R1ResultEaorCoordinator(
        port=R1ResultEaorProductPort(
            provisioning_factory=provisioning_factory,
            activation_factory=activation_factory,
            session_factory=session_factory,
        )
    )


__all__ = [
    "R1EaorProvisioningOwnerAdapter", "R1EaorRecoveryResumeAdapter",
    "R1EaorSessionOwnerAdapter",
    "R1ResultEaorProductPort", "build_dormant_product_eaor_coordinator",
]
