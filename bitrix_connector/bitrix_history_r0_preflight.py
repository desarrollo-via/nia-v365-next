"""Preflight one-shot e inyectable para fijar el ancla R0 sin leer historial."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Protocol

from .bitrix_history_r0_client import (
    BitrixHistoryDialog,
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
)
from .bitrix_history_r0_runner import (
    CONTROLLED_DIALOG_ID,
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
    _barriers_safe,
    _dialog_identity_checks,
    _verified_dialog,
)
from .config import ConnectorSettings


class BitrixHistoryPreflightReader(Protocol):
    async def get_dialog(self, dialog_id: str) -> BitrixHistoryReadResult: ...
    async def close(self) -> None: ...


BitrixHistoryPreflightClientFactory = Callable[
    [], Awaitable[BitrixHistoryPreflightReader]
]


class BitrixHistoryPreflightFactoryError(RuntimeError):
    """Comunica sólo estado de cierre, nunca detalles de credenciales."""

    _ALLOWED_REASONS = {
        "bitrix_history_preflight_failed_safe",
        "bitrix_history_resources_close_failed",
    }

    def __init__(self, reason: str, *, resources_closed: bool) -> None:
        if reason not in self._ALLOWED_REASONS:
            raise ValueError("bitrix_history_factory_reason_invalid")
        super().__init__(reason)
        self.reason = reason
        self.resources_closed = resources_closed


@dataclass(frozen=True, repr=False)
class BitrixHistoryR0Anchor:
    """Identidad efímera para continuar el flujo sin publicarla en la salida."""

    session_id: int
    baseline_last_message_id: int

    def __post_init__(self) -> None:
        if self.session_id <= 0 or self.baseline_last_message_id <= 0:
            raise ValueError("bitrix_history_anchor_invalid")

    def __repr__(self) -> str:
        return "BitrixHistoryR0Anchor(<redacted>)"


@dataclass(frozen=True)
class BitrixHistoryDialogIdentityDiagnostic:
    """Comparaciones redactadas; nunca conserva valores del diálogo."""

    chat_id_matches: bool
    dialog_id_matches: bool
    entity_type_matches: bool
    role_allowed: bool
    mismatch_count: int

    @classmethod
    def from_checks(
        cls,
        checks: tuple[bool, bool, bool, bool],
    ) -> "BitrixHistoryDialogIdentityDiagnostic":
        return cls(
            chat_id_matches=checks[0],
            dialog_id_matches=checks[1],
            entity_type_matches=checks[2],
            role_allowed=checks[3],
            mismatch_count=sum(not value for value in checks),
        )

    def __post_init__(self) -> None:
        values = (
            self.chat_id_matches,
            self.dialog_id_matches,
            self.entity_type_matches,
            self.role_allowed,
        )
        if any(type(value) is not bool for value in values):
            raise TypeError("bitrix_history_identity_diagnostic_invalid")
        if self.mismatch_count != sum(not value for value in values):
            raise ValueError("bitrix_history_identity_diagnostic_invalid")


@dataclass(frozen=True)
class BitrixHistoryR0PreflightOutcome:
    """Separa la salida allowlisted del ancla mantenida sólo en memoria."""

    result: BitrixHistoryR0Result
    _anchor: Optional[BitrixHistoryR0Anchor] = field(default=None, repr=False)
    _identity_diagnostic: Optional[
        BitrixHistoryDialogIdentityDiagnostic
    ] = field(default=None, repr=False)

    @property
    def anchor_available(self) -> bool:
        return self._anchor is not None

    def require_anchor(self) -> BitrixHistoryR0Anchor:
        if self._anchor is None:
            raise RuntimeError("bitrix_history_anchor_unavailable")
        return self._anchor

    @property
    def identity_diagnostic(self) -> Optional[BitrixHistoryDialogIdentityDiagnostic]:
        return self._identity_diagnostic


def _result(reason: str, **updates: object) -> BitrixHistoryR0Result:
    payload: dict[str, object] = {
        "status": BitrixHistoryR0Status.NO_GO,
        "reason": reason,
        "dialog_read_calls": 0,
        "history_read_calls": 0,
    }
    payload.update(updates)
    return BitrixHistoryR0Result(**payload)


def build_bitrix_history_r0_preflight_from_dialog(
    *,
    settings: ConnectorSettings,
    dialog: Optional[BitrixHistoryDialog],
    resources_closed: bool,
) -> BitrixHistoryR0PreflightOutcome:
    """Construye el ancla desde un diálogo ya leído, sin una segunda llamada."""

    if not _barriers_safe(settings):
        return BitrixHistoryR0PreflightOutcome(
            _result(
                "bitrix_history_barrier_degraded",
                resources_closed=resources_closed,
            )
        )
    if dialog is None or not _verified_dialog(dialog):
        diagnostic = None
        if dialog is not None:
            checks = _dialog_identity_checks(dialog)
            if checks is not None and not all(checks):
                diagnostic = BitrixHistoryDialogIdentityDiagnostic.from_checks(
                    checks
                )
        return BitrixHistoryR0PreflightOutcome(
            _result(
                "bitrix_history_dialog_mismatch",
                dialog_read_calls=1,
                resources_closed=resources_closed,
            ),
            _identity_diagnostic=diagnostic,
        )
    try:
        anchor = BitrixHistoryR0Anchor(
            session_id=dialog.session_id,
            baseline_last_message_id=dialog.last_message_id,
        )
    except ValueError:
        return BitrixHistoryR0PreflightOutcome(
            _result(
                "bitrix_history_session_identity_invalid",
                dialog_read_calls=1,
                dialog_verified=True,
                resources_closed=resources_closed,
            )
        )
    return BitrixHistoryR0PreflightOutcome(
        BitrixHistoryR0Result(
            status=BitrixHistoryR0Status.READY,
            reason="bitrix_history_preflight_ready",
            dialog_read_calls=1,
            history_read_calls=0,
            dialog_verified=True,
            session_verified=True,
            baseline_captured=True,
            resources_closed=resources_closed,
        ),
        anchor,
    )


async def execute_bitrix_history_r0_preflight_once(
    *,
    client_factory: BitrixHistoryPreflightClientFactory,
    settings: ConnectorSettings,
) -> BitrixHistoryR0PreflightOutcome:
    """Valida barreras y captura una sola ancla; nunca consulta historial."""

    if not _barriers_safe(settings):
        return BitrixHistoryR0PreflightOutcome(
            _result(
                "bitrix_history_barrier_degraded",
                resources_closed=True,
            )
        )

    client: Optional[BitrixHistoryPreflightReader] = None
    result = _result("bitrix_history_preflight_not_started")
    anchor: Optional[BitrixHistoryR0Anchor] = None
    identity_diagnostic: Optional[BitrixHistoryDialogIdentityDiagnostic] = None
    close_failed = False
    factory_resources_closed = True
    try:
        client = await client_factory()
        dialog_read = await client.get_dialog(CONTROLLED_DIALOG_ID)
        dialog = dialog_read.dialog
        verified_dialog = _verified_dialog(dialog)
        if (
            dialog_read.decision is not BitrixHistoryReadDecision.SUCCESS
            or not verified_dialog
        ):
            if (
                dialog_read.decision is BitrixHistoryReadDecision.SUCCESS
                and dialog is not None
            ):
                checks = _dialog_identity_checks(dialog)
                if checks is not None and not all(checks):
                    identity_diagnostic = (
                        BitrixHistoryDialogIdentityDiagnostic.from_checks(checks)
                    )
            result = _result(
                dialog_read.error_code or "bitrix_history_dialog_mismatch",
                dialog_read_calls=1,
            )
        else:
            try:
                anchor = BitrixHistoryR0Anchor(
                    session_id=dialog.session_id,
                    baseline_last_message_id=dialog.last_message_id,
                )
            except ValueError:
                result = _result(
                    "bitrix_history_session_identity_invalid",
                    dialog_read_calls=1,
                    dialog_verified=True,
                )
            else:
                result = BitrixHistoryR0Result(
                    status=BitrixHistoryR0Status.READY,
                    reason="bitrix_history_preflight_ready",
                    dialog_read_calls=1,
                    history_read_calls=0,
                    dialog_verified=True,
                    session_verified=True,
                    baseline_captured=True,
                )
    except BitrixHistoryPreflightFactoryError as exc:
        result = _result(exc.reason)
        anchor = None
        factory_resources_closed = exc.resources_closed
    except Exception:
        result = _result("bitrix_history_preflight_failed_safe")
        anchor = None
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                close_failed = True

    if close_failed:
        return BitrixHistoryR0PreflightOutcome(
            result.model_copy(
                update={
                    "status": BitrixHistoryR0Status.NO_GO,
                    "reason": "bitrix_history_resources_close_failed",
                    "resources_closed": False,
                }
            )
        )
    return BitrixHistoryR0PreflightOutcome(
        result.model_copy(update={"resources_closed": factory_resources_closed}),
        anchor,
        identity_diagnostic,
    )


__all__ = [
    "BitrixHistoryPreflightClientFactory",
    "BitrixHistoryPreflightFactoryError",
    "BitrixHistoryPreflightReader",
    "BitrixHistoryDialogIdentityDiagnostic",
    "BitrixHistoryR0Anchor",
    "BitrixHistoryR0PreflightOutcome",
    "build_bitrix_history_r0_preflight_from_dialog",
    "execute_bitrix_history_r0_preflight_once",
]
