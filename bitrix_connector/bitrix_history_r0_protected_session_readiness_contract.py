"""Alineación M33 de diagnóstico público del preflight protegido R0."""

from __future__ import annotations

from dataclasses import dataclass

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from .bitrix_history_r0_protected_preflight_composition import (
    PROTECTED_PREFLIGHT_FAILURE_CATEGORIES,
)


FUTURE_PROTECTED_SESSION_OWNER_MODULE = (
    "bitrix_connector.bitrix_history_r0_protected_preflight_execution_owner"
)
FUTURE_PROTECTED_SESSION_OWNER_COMMAND = (
    r'.\.venv\Scripts\python.exe -m '
    r'bitrix_connector.bitrix_history_r0_protected_preflight_execution_owner '
    r'--confirm-code "EJECUTAR PREFLIGHT R0 REAL PROTEGIDO UNA SOLA VEZ" '
    r'--dotenv-path .env'
)
FUTURE_PROTECTED_SESSION_AUTHORIZATION = (
    "AUTORIZACIÓN INDEPENDIENTE R0 — PREFLIGHT BITRIX DE SOLO LECTURA: "
    "Autorizo exclusivamente, después de verificar que el owner M33 figura "
    "command_available=true y owner_module_invocable=true, una ejecución única "
    "nueva e independiente del proceso propietario local de nia-next mediante "
    "el comando exacto congelado; la autorización M32 anterior permanece "
    "consumida y no se reutiliza. Autorizo una sola "
    "apertura interna de C:\\Users\\H\\Desktop\\f\\web\\phyton-codigo\\nia-next\\.env "
    "por AllowlistedDotenvSource para transferir únicamente NIA_BITRIX_DOMAIN, "
    "NIA_BITRIX_MEMBER_ID, NIA_BITRIX_CLIENT_ID, NIA_BITRIX_CLIENT_SECRET, "
    "NIA_BITRIX_MONGO_URI, NIA_BITRIX_MONGO_DB y "
    "NIA_BITRIX_INSTALLATIONS_COLLECTION, sin mostrar, copiar, transcribir, "
    "contar, validar ni registrar sus valores. Autorizo obtener una vez el OAuth "
    "almacenado sin renovarlo y realizar exactamente una lectura Bitrix "
    "imopenlines.dialog.get para chat78733, conservando sesión y "
    "last_message_id sólo en memoria como ancla privada. La salida queda limitada "
    "a estados, booleanos, contadores allowlisted y una failure_category elegida "
    "exclusivamente de la allowlist fija del contrato M33; cualquier categoría "
    "desconocida debe descartarse y terminar en fallo seguro. No autorizo lectura de "
    "historial, mensajes, Mongo fuera de la instalación OAuth, renovación OAuth, "
    "mutaciones, Bitrix config.update, bots, Línea 13, Wazzup, Azure, armado del "
    "lector, solicitud o envío de mensajes, NIA ni reintentos. Cualquier fuente, "
    "identidad, barrera, salida, timeout, error, cancelación o cierre ambiguo "
    "obliga a detenerse, limpiar en finally y terminar el proceso; no existe "
    "rollback externo porque la operación autorizada es sólo lectura."
)


@dataclass(frozen=True)
class ProtectedHistorySessionReadinessContract:
    phase: str = "M33"
    state: str = "READY-AWAITING-AUTHORIZATION"
    reason: str = "protected_preflight_failure_category_awaiting_new_authorization"
    m31_static_readiness_consumed: bool = True
    m32_authorization_consumed: bool = True
    m19_launcher_bound: bool = True
    m20_materializer_bound: bool = True
    m21_gate_owner_bound: bool = True
    m22_human_boundary_bound: bool = True
    chain_complete_in_doubles: bool = True
    source_kind: str = "local-dotenv-allowlisted-one-shot"
    source_path: str = ".env"
    protected_name_allowlist: tuple[str, ...] = PROTECTED_SETTING_NAMES
    source_open_authorized: bool = False
    owner_module: str = FUTURE_PROTECTED_SESSION_OWNER_MODULE
    owner_command: str = FUTURE_PROTECTED_SESSION_OWNER_COMMAND
    owner_module_present: bool = True
    fixture_command_available: bool = True
    real_ready_composition_bound: bool = True
    activation_delta_frozen: bool = True
    dormant_real_parser_adapter_bound: bool = True
    parser_contract_prepared_in_doubles: bool = True
    parser_real_enabled: bool = False
    dormant_builder_composition_bound: bool = True
    builder_contract_prepared_in_doubles: bool = True
    path_builder_bound: bool = True
    source_builder_bound: bool = True
    private_builder_bound: bool = True
    builder_real_enabled: bool = False
    outer_confirmation_composition_bound: bool = True
    outer_confirmation_prepared_in_doubles: bool = True
    outer_confirmation_default_enabled: bool = False
    outer_confirmation_attempt_limit: int = 1
    outer_confirmation_timeout_seconds: float = 300.0
    final_composition_audit_verified: bool = True
    rejection_terminal_verified: bool = True
    timeout_terminal_verified: bool = True
    cancellation_terminal_verified: bool = True
    cleanup_verified_in_doubles: bool = True
    technical_readiness_closed: bool = True
    owner_complete: bool = True
    command_available: bool = True
    command_indicator_static_only: bool = False
    owner_module_invocable: bool = True
    command_invocation_authorized: bool = False
    authorization_request_ready: bool = True
    selected_preflight_owner: bool = True
    session_fixture_cli_preserved: bool = True
    failure_category_allowlist_bound: bool = True
    failure_category_allowlist: tuple[str, ...] = tuple(
        sorted(PROTECTED_PREFLIGHT_FAILURE_CATEGORIES)
    )
    repeat_authorization_required: bool = True
    legacy_handoff_cli_is_owner: bool = False
    fixture_helper_cli_is_owner: bool = False
    authorization_template_frozen: bool = True
    authorization_ready_for_use: bool = True
    real_execution_authorized: bool = False
    message_request_authorized: bool = False


PROTECTED_HISTORY_SESSION_READINESS_CONTRACT = (
    ProtectedHistorySessionReadinessContract()
)


__all__ = [
    "FUTURE_PROTECTED_SESSION_AUTHORIZATION",
    "FUTURE_PROTECTED_SESSION_OWNER_COMMAND",
    "FUTURE_PROTECTED_SESSION_OWNER_MODULE",
    "PROTECTED_HISTORY_SESSION_READINESS_CONTRACT",
    "ProtectedHistorySessionReadinessContract",
]
