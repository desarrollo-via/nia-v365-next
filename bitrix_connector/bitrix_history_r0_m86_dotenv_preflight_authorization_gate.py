"""M86-BK: compuerta one-shot de preflight, aún sin binding real ejecutable."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .bitrix_history_r0_m86_combined_preflight_owner import (
    M86CombinedPreflightSnapshot,
)
from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


M86BK_AUTHORIZATION_LITERAL = (
    "AUTORIZACIÓN PREFLIGHT M86-BK — UNA SOLA EJECUCIÓN DE SOLO LECTURA: "
    "Autorizo exclusivamente una única apertura protegida del archivo .env del "
    "PROJECT_ROOT de nia-next para transferir sólo estas siete claves exactas: "
    + ", ".join(PROTECTED_SETTING_NAMES)
    + ". Autorizo una sola carga del OAuth almacenado, sin renovarlo, y "
    "exactamente cuatro lecturas Bitrix de preflight: imbot.v2.Revision.get, "
    "imbot.v2.Bot.list, imopenlines.dialog.get para chat78733 e "
    "imopenlines.config.get para Línea 13, únicamente para verificar bot 373259, "
    "chat78733 y Línea 13. No autorizo historial, NIA, mensajes, escrituras, "
    "borrados, reintentos, cambios productivos ni mostrar valores o respuestas "
    "privadas. Autorizo una única salida pública limitada a estados, booleanos "
    "y contadores del contrato y una failure_category elegida exclusivamente "
    "entre none, owner_factory_unavailable, preflight_no_go, source_stage, "
    "oauth_stage, bot_stage, bot_revision_stage, "
    "bot_revision_transport_stage, bot_revision_remote_stage, "
    "bot_revision_token_expired_stage, bot_revision_retryable_stage, "
    "bot_revision_permanent_stage, bot_revision_contract_stage, "
    "bot_list_stage, bot_contract_stage, dialog_stage, contract_stage, "
    "cleanup_ambiguous o cancelled. Todos los "
    "buffers y recursos deben limpiarse y cerrarse en "
    "finally; cualquier deriva o cierre ambiguo consume la autorización y "
    "termina en NO-GO."
)

M86BKFailureCategory = Literal[
    "none",
    "authorization_invalid",
    "owner_factory_unavailable",
    "preflight_no_go",
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
    "cleanup_ambiguous",
    "cancelled",
    "gate_reused",
]


class M86BKPreflightOwner(Protocol):
    async def run_once(self) -> M86CombinedPreflightSnapshot: ...


M86BKOwnerFactory = Callable[[], M86BKPreflightOwner]


class _M86BKFactoryPermit:
    """Capacidad efímera emitida sólo después de validar el literal exacto."""

    __slots__ = ()


@dataclass(frozen=True)
class M86BKAuthorizationContract:
    phase: Literal["M86-BK"] = "M86-BK"
    state: Literal["PREPARED-NOT-SHOWN"] = "PREPARED-NOT-SHOWN"
    exact_literal: str = M86BK_AUTHORIZATION_LITERAL
    shown_to_person: Literal[False] = False
    authorization_received: Literal[False] = False
    linked_to_real_execution: Literal[False] = False
    current_real_open_budget: Literal[0] = 0
    current_oauth_budget: Literal[0] = 0
    current_bitrix_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0

    def accepts(self, candidate: str) -> bool:
        return type(candidate) is str and candidate == self.exact_literal


@dataclass(frozen=True)
class M86BKGateSnapshot:
    phase: Literal["M86-BK"] = "M86-BK"
    state: Literal["VERIFIED", "NO-GO", "CANCELLED"] = "NO-GO"
    failure_category: M86BKFailureCategory = "preflight_no_go"
    authorization_exact: bool = False
    authorization_consumed: bool = False
    owner_factory_calls: int = 0
    owner_calls: int = 0
    combined_preflight_verified: bool = False
    private_resources_closed: bool = True
    fixture_execution: bool = True
    real_path_bound: bool = False
    real_path_opened: bool = False
    linked_to_real_execution: bool = False
    oauth_refresh_calls: Literal[0] = 0
    history_read_calls: Literal[0] = 0
    messages_sent: Literal[0] = 0
    bitrix_written: Literal[False] = False
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    external_calls: Literal[0] = 0


class M86BKFixtureAuthorizationGate:
    """Compuerta one-shot con perfil fixture predeterminado o real explícito."""

    __slots__ = ("_execution_profile", "_owner_factory", "_used")

    def __init__(
        self,
        *,
        owner_factory: M86BKOwnerFactory,
        execution_profile: Literal["fixture", "real"] = "fixture",
    ) -> None:
        if not callable(owner_factory) or execution_profile not in ("fixture", "real"):
            raise TypeError("m86bk_owner_factory_invalid")
        self._owner_factory: M86BKOwnerFactory | None = owner_factory
        self._execution_profile = execution_profile
        self._used = False

    def _snapshot(self, **values) -> M86BKGateSnapshot:
        return M86BKGateSnapshot(
            fixture_execution=self._execution_profile == "fixture",
            real_path_bound=self._execution_profile == "real",
            linked_to_real_execution=self._execution_profile == "real",
            **values,
        )

    async def run_once(self, *, confirm_code: str) -> M86BKGateSnapshot:
        if self._used or self._owner_factory is None:
            self._used = True
            return self._snapshot(failure_category="gate_reused")
        self._used = True
        authorization = M86BKAuthorizationContract()
        if not authorization.accepts(confirm_code):
            self._owner_factory = None
            return self._snapshot(
                failure_category="authorization_invalid",
                authorization_consumed=True,
            )
        factory, self._owner_factory = self._owner_factory, None
        try:
            permitted_builder = getattr(factory, "build_after_gate_once", None)
            owner = (
                permitted_builder(_M86BKFactoryPermit())
                if callable(permitted_builder)
                else factory()
            )
        except BaseException:
            return self._snapshot(
                failure_category="owner_factory_unavailable",
                authorization_exact=True,
                authorization_consumed=True,
                owner_factory_calls=1,
            )
        if not callable(getattr(owner, "run_once", None)):
            return self._snapshot(
                failure_category="owner_factory_unavailable",
                authorization_exact=True,
                authorization_consumed=True,
                owner_factory_calls=1,
            )
        try:
            result = await owner.run_once()
        except asyncio.CancelledError:
            return self._snapshot(
                state="CANCELLED",
                failure_category="cancelled",
                authorization_exact=True,
                authorization_consumed=True,
                owner_factory_calls=1,
                owner_calls=1,
            )
        except BaseException:
            return self._snapshot(
                failure_category="preflight_no_go",
                authorization_exact=True,
                authorization_consumed=True,
                owner_factory_calls=1,
                owner_calls=1,
            )
        if type(result) is not M86CombinedPreflightSnapshot:
            return self._snapshot(
                failure_category="preflight_no_go",
                authorization_exact=True,
                authorization_consumed=True,
                owner_factory_calls=1,
                owner_calls=1,
            )
        closed = result.private_resources_closed is True
        verified = (
            result.state == "VERIFIED"
            and result.combined_preflight_verified
            and result.history_anchor_available
            and closed
            and result.oauth_refresh_calls == 0
            and result.history_read_calls == 0
            and result.messages_sent == 0
            and result.bitrix_written is False
            and result.persisted is False
            and result.nia_next_called is False
        )
        safe_stage_categories: tuple[M86BKFailureCategory, ...] = (
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
        )
        failure_category: M86BKFailureCategory = "none"
        if not verified:
            if not closed or result.failure_stage == "cleanup_stage":
                failure_category = "cleanup_ambiguous"
            elif result.failure_stage in safe_stage_categories:
                failure_category = result.failure_stage
            else:
                failure_category = "preflight_no_go"
        return self._snapshot(
            state="VERIFIED" if verified else "NO-GO",
            failure_category=failure_category,
            authorization_exact=True,
            authorization_consumed=True,
            owner_factory_calls=1,
            owner_calls=1,
            combined_preflight_verified=verified,
            private_resources_closed=closed,
            real_path_opened=(
                self._execution_profile == "real"
                and result.credential_source_read_calls == 7
            ),
        )


M86BKAuthorizationGate = M86BKFixtureAuthorizationGate


__all__ = [
    "M86BK_AUTHORIZATION_LITERAL",
    "M86BKAuthorizationGate",
    "M86BKAuthorizationContract",
    "M86BKFixtureAuthorizationGate",
    "M86BKGateSnapshot",
]
