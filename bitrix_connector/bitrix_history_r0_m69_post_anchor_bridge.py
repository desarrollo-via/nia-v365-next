"""Puente M69 hermético: ancla M68 -> una lectura -> entrada M62."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .bitrix_history_r0_exact_scope_composition import (
    run_exact_controlled_roundtrip_with_rollback,
)
from .bitrix_history_r0_isolated_roundtrip import (
    InjectedBitrixSender,
    InjectedNiaSender,
)
from .bitrix_history_r0_m68_combined_preflight import CombinedR1PreflightAdapter
from .bitrix_history_r0_real_roundtrip_plan import ProtectedRealRoundtripPlan
from .bitrix_history_r0_reply_rollback_adapter import (
    InjectedPostDeleteHistoryReader,
    InjectedReplyDeleter,
)
from .bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripStatus,
    InjectedPostSendHistoryReader,
)


class InjectedPostAnchorHistoryReader(Protocol):
    async def read_post_anchor_history(self, *, session_id: int) -> object: ...


class PostAnchorBridgeStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ROLLED_BACK = "ROLLED-BACK"
    NO_GO = "NO-GO"


class PostAnchorBridgeResult(BaseModel):
    """Evidencia pública sin ancla, payload, texto ni respuesta."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["M69"] = "M69"
    status: PostAnchorBridgeStatus
    reason: Literal[
        "m69_exact_scope_verified",
        "m69_exact_scope_rolled_back",
        "m69_exact_scope_no_go",
        "m69_preflight_unavailable",
        "m69_post_anchor_history_failed",
        "m69_exact_scope_failed",
        "m69_reuse_rejected",
    ]
    history_read_count: int = Field(ge=0, le=1)
    exact_scope_call_count: int = Field(ge=0, le=1)
    private_state_cleared: Literal[True] = True
    payload_retained: Literal[False] = False
    no_retry: Literal[True] = True
    dependencies_injected: Literal[True] = True
    fixture_only: Literal[True] = True
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    authorization_present: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    actual_connection_proven: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class PostAnchorExactScopeBridge:
    """Consume M68 y todas las dependencias inyectadas una única vez."""

    def __init__(
        self,
        *,
        plan: ProtectedRealRoundtripPlan,
        preflight_adapter: CombinedR1PreflightAdapter,
        history_reader: InjectedPostAnchorHistoryReader,
        nia_sender: InjectedNiaSender,
        bitrix_sender: InjectedBitrixSender,
        post_send_history_reader: InjectedPostSendHistoryReader,
        deleter: InjectedReplyDeleter,
        post_delete_history_reader: InjectedPostDeleteHistoryReader,
        expected_sender_id: Optional[int] = None,
        emergency_rollback: bool = False,
    ) -> None:
        dependencies = (
            preflight_adapter,
            history_reader,
            nia_sender,
            bitrix_sender,
            post_send_history_reader,
            deleter,
            post_delete_history_reader,
        )
        if (
            not isinstance(plan, ProtectedRealRoundtripPlan)
            or not isinstance(preflight_adapter, CombinedR1PreflightAdapter)
            or any(item is None for item in dependencies)
        ):
            raise ValueError("m69_bridge_contract_invalid")
        self._dependencies: Optional[tuple[object, ...]] = (
            plan,
            *dependencies,
            expected_sender_id,
            emergency_rollback,
        )
        self._used = False

    def clear(self) -> None:
        self._dependencies = None

    @property
    def cleared(self) -> bool:
        return self._dependencies is None

    @staticmethod
    def _result(
        reason: str,
        *,
        history_reads: int,
        exact_scope_calls: int,
        verified: bool = False,
        rolled_back: bool = False,
    ) -> PostAnchorBridgeResult:
        return PostAnchorBridgeResult(
            status=(
                PostAnchorBridgeStatus.ROLLED_BACK
                if rolled_back
                else (
                    PostAnchorBridgeStatus.VERIFIED
                    if verified
                    else PostAnchorBridgeStatus.NO_GO
                )
            ),
            reason=reason,
            history_read_count=history_reads,
            exact_scope_call_count=exact_scope_calls,
        )

    async def run_once(self) -> PostAnchorBridgeResult:
        if self._used or self._dependencies is None:
            self.clear()
            return self._result(
                "m69_reuse_rejected", history_reads=0, exact_scope_calls=0
            )
        self._used = True
        dependencies = self._dependencies
        self.clear()
        payload: object = None
        history_reads = 0
        exact_scope_calls = 0
        try:
            (
                plan,
                preflight_adapter,
                history_reader,
                nia_sender,
                bitrix_sender,
                post_send_history_reader,
                deleter,
                post_delete_history_reader,
                expected_sender_id,
                emergency_rollback,
            ) = dependencies
            try:
                preflight = preflight_adapter.take_history_outcome_once()
                anchor = preflight.require_anchor()
            except Exception:
                preflight_adapter.clear()
                return self._result(
                    "m69_preflight_unavailable",
                    history_reads=0,
                    exact_scope_calls=0,
                )

            history_reads = 1
            try:
                payload = await history_reader.read_post_anchor_history(
                    session_id=anchor.session_id
                )
            except Exception:
                return self._result(
                    "m69_post_anchor_history_failed",
                    history_reads=1,
                    exact_scope_calls=0,
                )

            exact_scope_calls = 1
            try:
                composed = await run_exact_controlled_roundtrip_with_rollback(
                    plan=plan,
                    preflight=preflight,
                    payload=payload,
                    nia_sender=nia_sender,
                    bitrix_sender=bitrix_sender,
                    post_send_history_reader=post_send_history_reader,
                    deleter=deleter,
                    post_delete_history_reader=post_delete_history_reader,
                    expected_sender_id=expected_sender_id,
                    emergency_rollback=emergency_rollback,
                )
            except Exception:
                return self._result(
                    "m69_exact_scope_failed",
                    history_reads=1,
                    exact_scope_calls=1,
                )
            verified = composed.status is ComposedRoundtripStatus.VERIFIED
            rolled_back = composed.status is ComposedRoundtripStatus.ROLLED_BACK
            return self._result(
                (
                    "m69_exact_scope_verified"
                    if verified
                    else (
                        "m69_exact_scope_rolled_back"
                        if rolled_back
                        else "m69_exact_scope_no_go"
                    )
                ),
                history_reads=1,
                exact_scope_calls=1,
                verified=verified,
                rolled_back=rolled_back,
            )
        finally:
            payload = None
            dependencies = ()
            self.clear()


__all__ = [
    "InjectedPostAnchorHistoryReader",
    "PostAnchorBridgeResult",
    "PostAnchorBridgeStatus",
    "PostAnchorExactScopeBridge",
]
