"""Superficie HTTP aislada y bloqueada en ``off``."""

from fastapi import APIRouter, Request

from . import CONNECTOR_VERSION
from .audit_router import create_audit_router
from .config import load_settings
from .bitrix_event_scoped_r1_pre_event_binding import (
    mount_optional_event_scoped_r1_with_pre_event_binding,
)
from .installation_router import create_installation_router
from .installation_status_router import create_installation_status_router
from .models import (
    ConnectorHealth,
    WebhookReceipt,
)
from .h1_visible import create_h1_visible_router, h1_visible_buffer
from .openline_r0_bridge_mount import (
    R0_BRIDGE_EMBEDDED_PREFIX,
    mount_optional_r0_bridge_fail_isolated,
)
from .review_decision_http import (
    REVIEW_DECISION_MOUNT_PREFIX,
    build_review_decision_router,
)
from .review_decision_runtime import ReviewDecisionRuntime
from .r1_key_vault_protected_host_probe_binding import (
    build_protected_host_probe,
)
from .r1_activation_host_preflight import build_r1_activation_host_preflight
from .runtime import ConnectorRuntime
from .review_router import create_review_router
from .webhook_handler import handle_bitrix_webhook


router = APIRouter(prefix="/bitrix-connector", tags=["Bitrix Connector"])
connector_runtime = ConnectorRuntime()
review_decision_runtime = ReviewDecisionRuntime()
protected_host_probe = build_protected_host_probe()
provisioning_preflight_probe = build_protected_host_probe()
activation_preflight_probe = build_r1_activation_host_preflight()
router.include_router(create_installation_router())
router.include_router(create_installation_status_router())
router.include_router(
    create_review_router(
        connector_runtime,
        include_decisions=False,
        host_probe=protected_host_probe,
        provisioning_probe=provisioning_preflight_probe,
        activation_preflight=activation_preflight_probe,
    )
)
router.include_router(
    build_review_decision_router(
        review_decision_runtime,
        prefix=REVIEW_DECISION_MOUNT_PREFIX,
    )
)
router.include_router(create_audit_router())
router.include_router(create_h1_visible_router())
embedded_r0_bridge_mount = mount_optional_r0_bridge_fail_isolated(
    router,
    load_settings(),
    prefix=R0_BRIDGE_EMBEDDED_PREFIX,
)
event_scoped_r1_mount = mount_optional_event_scoped_r1_with_pre_event_binding(
    router,
    load_settings(),
)


async def observe_inert_receipt(event, receipt, settings) -> None:
    """Aisla los observadores pasivos; ninguno puede bloquear al webhook."""
    for observer in (embedded_r0_bridge_mount.receipt_observer, h1_visible_buffer.observe):
        if observer is None:
            continue
        try:
            await observer(event, receipt, settings)
        except Exception:
            pass


async def start_connector_runtime() -> None:
    await connector_runtime.start(load_settings())


async def stop_connector_runtime() -> None:
    await connector_runtime.close()


async def start_review_decision_runtime() -> None:
    await review_decision_runtime.start(load_settings())


async def stop_review_decision_runtime() -> None:
    await review_decision_runtime.close()


router.add_event_handler("startup", start_connector_runtime)
router.add_event_handler("startup", start_review_decision_runtime)
router.add_event_handler("shutdown", stop_review_decision_runtime)
router.add_event_handler("shutdown", stop_connector_runtime)


@router.get("/health", response_model=ConnectorHealth)
async def connector_health() -> ConnectorHealth:
    settings = load_settings()
    runtime = connector_runtime.snapshot
    return ConnectorHealth(
        status="ok",
        module="bitrix_connector",
        version=CONNECTOR_VERSION,
        requested_mode=settings.requested_mode,
        effective_mode=settings.effective_mode.value,
        activation_locked=settings.activation_locked,
        external_calls_enabled=settings.external_calls_enabled,
        runtime_state=runtime.state.value,
        runtime_service_available=runtime.service_available,
        runtime_resources_available=runtime.resources_available,
        configured=settings.configured,
        pilot=settings.pilot_summary,
        r0_bridge={
            "requested": embedded_r0_bridge_mount.requested,
            "mounted": embedded_r0_bridge_mount.enabled,
            "status": embedded_r0_bridge_mount.status,
            "reason": embedded_r0_bridge_mount.reason,
        },
        warnings=list(settings.warnings),
    )


@router.post("/webhook", response_model=WebhookReceipt)
async def bitrix_webhook(request: Request):
    """
    Inspecciona un evento sin persistirlo ni ejecutar acciones externas.

    El endpoint existe para validar el contrato real de Bitrix mientras el
    conector sigue bloqueado en ``off``.
    """
    return await handle_bitrix_webhook(
        request,
        settings_loader=load_settings,
        runtime=connector_runtime,
        receipt_observer=observe_inert_receipt,
        protected_oauth_observer=event_scoped_r1_mount.observer,
    )
