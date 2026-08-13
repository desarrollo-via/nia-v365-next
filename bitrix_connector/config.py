"""Configuración aislada y segura del conector Bitrix–NIA."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Mapping, Optional

from pydantic import ValidationError

from .pilot_scope import PilotScopeRule
from .modes import ConnectorMode

DEFAULT_MONGO_DB = "nia"
DEFAULT_EVENTS_COLLECTION = "nia_bitrix_events"
DEFAULT_INSTALLATIONS_COLLECTION = "nia_bitrix_installations"
DEFAULT_REVIEW_AUDIT_COLLECTION = "nia_bitrix_review_audit"
EVENT_R1_PARTICIPANT_STRATEGY_POSTERIOR = "posterior"
EVENT_R1_PARTICIPANT_STRATEGY_PRE_EVENT = "pre-event"
EVENT_R1_PARTICIPANT_STRATEGIES = frozenset(
    {
        EVENT_R1_PARTICIPANT_STRATEGY_POSTERIOR,
        EVENT_R1_PARTICIPANT_STRATEGY_PRE_EVENT,
    }
)


@dataclass(frozen=True)
class ConnectorSettings:
    requested_mode: str
    effective_mode: ConnectorMode
    activation_locked: bool
    nia_base_url: Optional[str]
    g0_public_origin: Optional[str]
    bitrix_domain: Optional[str]
    bitrix_member_id: Optional[str]
    bitrix_application_token: Optional[str]
    review_token: Optional[str]
    review_actor: Optional[str]
    review_credential_id: Optional[str]
    review_audit_collection: str
    mongo_uri: Optional[str]
    mongo_db: str
    events_collection: str
    installations_collection: str
    bitrix_client_id: Optional[str]
    bitrix_client_secret: Optional[str]
    key_vault_url: Optional[str]
    installation_enabled: bool
    installation_configuration_valid: bool
    r0_bridge_enabled: bool
    r0_bridge_configuration_valid: bool
    event_r1_enabled: bool
    event_r1_configuration_valid: bool
    event_r1_participant_strategy: str
    event_r1_participant_strategy_configuration_valid: bool
    pilot_enabled: bool
    pilot_emergency_stop: bool
    pilot_rules: tuple[PilotScopeRule, ...]
    pilot_configuration_valid: bool
    warnings: tuple[str, ...]

    @property
    def external_calls_enabled(self) -> bool:
        return False

    @property
    def configured(self) -> dict[str, bool]:
        return {
            "nia_base_url": bool(self.nia_base_url),
            "bitrix_domain": bool(self.bitrix_domain),
            "bitrix_member_id": bool(self.bitrix_member_id),
            "bitrix_application_token": bool(self.bitrix_application_token),
            "review_token": bool(self.review_token),
        }

    @property
    def review_decision_configured(self) -> dict[str, bool]:
        return {
            "review_token": bool(self.review_token),
            "review_actor": bool(self.review_actor),
            "review_credential_id": bool(self.review_credential_id),
            "review_audit_collection": bool(self.review_audit_collection),
        }

    @property
    def oauth_configured(self) -> dict[str, bool]:
        return {
            "bitrix_client_id": bool(self.bitrix_client_id),
            "bitrix_client_secret": bool(self.bitrix_client_secret),
            "installations_collection": bool(self.installations_collection),
        }

    @property
    def pilot_summary(self) -> dict[str, object]:
        return {
            "enabled": self.pilot_enabled,
            "emergency_stop": self.pilot_emergency_stop,
            "rule_count": len(self.pilot_rules),
            "configuration_valid": self.pilot_configuration_valid,
        }

    @property
    def storage_configured(self) -> dict[str, bool]:
        """Disponibilidad interna; no expone valores ni modifica el health."""
        return {
            "mongo_uri": bool(self.mongo_uri),
            "mongo_db": bool(self.mongo_db),
            "events_collection": bool(self.events_collection),
            "review_audit_collection": bool(self.review_audit_collection),
            "installations_collection": bool(self.installations_collection),
        }


def _clean_optional(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _first_clean(*values: Optional[str]) -> Optional[str]:
    for value in values:
        cleaned = _clean_optional(value)
        if cleaned:
            return cleaned
    return None


def _strict_bool(
    value: Optional[str],
    *,
    default: bool,
) -> tuple[bool, bool]:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return default, True
    if cleaned in {"1", "true", "yes", "on"}:
        return True, True
    if cleaned in {"0", "false", "no", "off"}:
        return False, True
    return default, False


def _pilot_rules(
    raw_json: Optional[str],
) -> tuple[tuple[PilotScopeRule, ...], bool]:
    cleaned = (raw_json or "").strip()
    if not cleaned:
        return (), True
    try:
        payload = json.loads(cleaned)
        if not isinstance(payload, list):
            return (), False
        return tuple(
            PilotScopeRule.model_validate(item)
            for item in payload
        ), True
    except (TypeError, ValueError, ValidationError):
        return (), False


def load_settings(environ: Optional[Mapping[str, str]] = None) -> ConnectorSettings:
    """
    Carga configuración sin habilitar comportamiento externo.

    Este primer corte mantiene el modo efectivo en ``off`` incluso si el
    entorno solicita otro modo. La activación se desbloqueará únicamente en un
    cambio posterior, probado y aprobado.
    """
    env = os.environ if environ is None else environ
    requested = (env.get("NIA_BITRIX_MODE") or ConnectorMode.OFF.value).strip().lower()
    warnings: list[str] = []
    pilot_enabled, enabled_valid = _strict_bool(
        env.get("NIA_BITRIX_PILOT_ENABLED"),
        default=False,
    )
    pilot_emergency_stop, stop_valid = _strict_bool(
        env.get("NIA_BITRIX_PILOT_EMERGENCY_STOP"),
        default=True,
    )
    pilot_rules, rules_valid = _pilot_rules(
        env.get("NIA_BITRIX_PILOT_RULES_JSON")
    )
    pilot_configuration_valid = enabled_valid and stop_valid and rules_valid
    installation_enabled, installation_enabled_valid = _strict_bool(
        env.get("NIA_BITRIX_INSTALLATION_ENABLED"),
        default=False,
    )
    r0_bridge_enabled, r0_bridge_enabled_valid = _strict_bool(
        env.get("NIA_BITRIX_R0_BRIDGE_ENABLED"),
        default=False,
    )
    event_r1_enabled, event_r1_enabled_valid = _strict_bool(
        env.get("NIA_BITRIX_EVENT_R1_ENABLED"),
        default=False,
    )
    requested_participant_strategy = (
        env.get("NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY")
        or EVENT_R1_PARTICIPANT_STRATEGY_POSTERIOR
    ).strip().lower()
    participant_strategy_valid = (
        requested_participant_strategy in EVENT_R1_PARTICIPANT_STRATEGIES
    )
    event_r1_participant_strategy = (
        requested_participant_strategy
        if participant_strategy_valid
        else EVENT_R1_PARTICIPANT_STRATEGY_POSTERIOR
    )

    valid_modes = {mode.value for mode in ConnectorMode}
    if requested not in valid_modes:
        warnings.append("invalid_requested_mode")
    elif requested != ConnectorMode.OFF.value:
        warnings.append("activation_locked_by_skeleton")
    if not enabled_valid:
        warnings.append("invalid_pilot_enabled")
    if not stop_valid:
        warnings.append("invalid_pilot_emergency_stop")
    if not rules_valid:
        warnings.append("invalid_pilot_rules_json")
    if pilot_enabled and not pilot_rules:
        warnings.append("pilot_scope_enabled_without_rules")
        pilot_configuration_valid = False
    if not installation_enabled_valid:
        warnings.append("invalid_installation_enabled")
    if not r0_bridge_enabled_valid:
        warnings.append("invalid_r0_bridge_enabled")
    if not event_r1_enabled_valid:
        warnings.append("invalid_event_r1_enabled")
    if not participant_strategy_valid:
        warnings.append("invalid_event_r1_participant_strategy")

    return ConnectorSettings(
        requested_mode=requested,
        effective_mode=ConnectorMode.OFF,
        activation_locked=True,
        nia_base_url=_clean_optional(env.get("NIA_BASE_URL")),
        g0_public_origin=_clean_optional(
            env.get("NIA_BITRIX_G0_PUBLIC_ORIGIN")
        ),
        bitrix_domain=_clean_optional(env.get("NIA_BITRIX_DOMAIN")),
        bitrix_member_id=_clean_optional(env.get("NIA_BITRIX_MEMBER_ID")),
        bitrix_application_token=_clean_optional(env.get("NIA_BITRIX_APPLICATION_TOKEN")),
        review_token=_clean_optional(env.get("NIA_BITRIX_REVIEW_TOKEN")),
        review_actor=_clean_optional(env.get("NIA_BITRIX_REVIEW_ACTOR")),
        review_credential_id=_clean_optional(
            env.get("NIA_BITRIX_REVIEW_CREDENTIAL_ID")
        ),
        review_audit_collection=_clean_optional(
            env.get("NIA_BITRIX_REVIEW_AUDIT_COLLECTION")
        )
        or DEFAULT_REVIEW_AUDIT_COLLECTION,
        mongo_uri=_first_clean(env.get("NIA_BITRIX_MONGO_URI"), env.get("MONGO_URI")),
        mongo_db=_first_clean(env.get("NIA_BITRIX_MONGO_DB"), env.get("MONGO_DB"))
        or DEFAULT_MONGO_DB,
        events_collection=_clean_optional(env.get("NIA_BITRIX_EVENTS_COLLECTION"))
        or DEFAULT_EVENTS_COLLECTION,
        installations_collection=_clean_optional(
            env.get("NIA_BITRIX_INSTALLATIONS_COLLECTION")
        )
        or DEFAULT_INSTALLATIONS_COLLECTION,
        bitrix_client_id=_clean_optional(env.get("NIA_BITRIX_CLIENT_ID")),
        bitrix_client_secret=_clean_optional(env.get("NIA_BITRIX_CLIENT_SECRET")),
        key_vault_url=_clean_optional(env.get("NIA_BITRIX_KEY_VAULT_URL")),
        installation_enabled=installation_enabled,
        installation_configuration_valid=installation_enabled_valid,
        r0_bridge_enabled=r0_bridge_enabled,
        r0_bridge_configuration_valid=r0_bridge_enabled_valid,
        event_r1_enabled=event_r1_enabled,
        event_r1_configuration_valid=event_r1_enabled_valid,
        event_r1_participant_strategy=event_r1_participant_strategy,
        event_r1_participant_strategy_configuration_valid=(
            participant_strategy_valid
        ),
        pilot_enabled=pilot_enabled,
        pilot_emergency_stop=pilot_emergency_stop,
        pilot_rules=pilot_rules,
        pilot_configuration_valid=pilot_configuration_valid,
        warnings=tuple(warnings),
    )
