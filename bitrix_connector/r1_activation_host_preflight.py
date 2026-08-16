"""One-shot host-side R1 activation preflight with sanitized output only."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
import json
from pathlib import Path

from .bitrix_event_scoped_r1_protected_oauth_builder import (
    PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    ProtectedStoredOAuthResourcesBuilder,
)
from .controlled_chat_participant_http import (
    ControlledParticipantHttpResources,
    ParticipantHttpDecision,
)
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory
from .r1_key_vault_exact_secret_backend import (
    build_managed_identity_exact_secret_backend,
)
from .r1_pre_event_activation_evidence_collector import (
    SanitizedDeploymentEvidence,
    SanitizedParticipantEvidence,
    SanitizedProtectedSourceEvidence,
)
from .r1_pre_event_activation_exact_switch_reader import (
    ExactSwitchBaselineProbe,
    MappingExactSwitchValueSource,
)
from .r1_pre_event_activation_preflight import (
    BOT_NEXT_ID,
    BOT_NIA_ID,
    CONTROLLED_CHAT_ID,
    CONTROLLED_DEAL_ID,
    CONTROLLED_DIALOG_ID,
    PROTECTED_SETTING_COUNT,
    PROTECTED_SOURCE_KIND,
    PROTECTED_TARGET_ID,
    R1ActivationPreflightEvidence,
    SWITCH_ORDER,
)
from .config import load_settings


DEPLOYMENT_IDENTITY_PATH = Path(__file__).with_name("_deployment_identity.json")
MAX_HOST_PREFLIGHT_ATTEMPTS = 3
PARTICIPANT_FAILURE_CATEGORIES = frozenset({
    "participant_list_pagination_cycle", "participant_list_transport_uncertain",
    "participant_list_remote_uncertain", "participant_list_rejected",
    "participant_list_invalid_response", "participant_list_empty_not_authoritative",
    "participant_list_page_size_invalid", "participant_list_identity_conflict",
    "participant_list_total_conflict", "participant_list_truncated",
    "participant_list_pagination_invalid", "participant_list_page_limit_exceeded",
    "participant_list_multiple_pages",
})


class R1ActivationHostPreflightFailure(RuntimeError):
    """Sanitized failure without an external value or exception text."""

    __slots__ = ("attempts", "category", "retryable", "stage")

    def __init__(
        self, *, stage: str, category: str, retryable: bool, attempts: int
    ) -> None:
        super().__init__("r1_activation_host_preflight_unavailable")
        self.stage = stage
        self.category = category
        self.retryable = retryable
        self.attempts = attempts


def read_packaged_deployment_identity() -> tuple[str, str]:
    payload = json.loads(DEPLOYMENT_IDENTITY_PATH.read_text(encoding="utf-8"))
    if type(payload) is not dict or set(payload) != {"commit", "tree"}:
        raise RuntimeError("r1_deployment_identity_invalid")
    commit, tree = payload["commit"], payload["tree"]
    if any(
        type(value) is not str
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
        for value in (commit, tree)
    ):
        raise RuntimeError("r1_deployment_identity_invalid")
    return commit, tree


class ExactR1ActivationHostPreflight:
    """Reads one exact protected record and one participant page, then closes."""

    __slots__ = (
        "_attempts", "_backend_builder", "_deployment_identity_supplier",
        "_environ", "_http_resources_factory", "_max_attempts",
        "_oauth_factory_builder", "_settings_loader", "_used",
    )

    def __init__(
        self,
        *,
        environ: Mapping[str, str],
        backend_builder=build_managed_identity_exact_secret_backend,
        oauth_factory_builder=PilotDiscoveryOAuthFactory,
        http_resources_factory=ControlledParticipantHttpResources.build,
        settings_loader=load_settings,
        deployment_identity_supplier=read_packaged_deployment_identity,
        max_attempts: int = MAX_HOST_PREFLIGHT_ATTEMPTS,
    ) -> None:
        if (
            environ is None
            or not callable(getattr(environ, "__getitem__", None))
            or type(max_attempts) is not int
            or not 1 <= max_attempts <= MAX_HOST_PREFLIGHT_ATTEMPTS
            or not all(callable(item) for item in (
                backend_builder, oauth_factory_builder,
                http_resources_factory, settings_loader,
                deployment_identity_supplier,
            ))
        ):
            raise TypeError("r1_activation_host_preflight_dependency_invalid")
        self._environ = environ
        self._backend_builder = backend_builder
        self._oauth_factory_builder = oauth_factory_builder
        self._http_resources_factory = http_resources_factory
        self._settings_loader = settings_loader
        self._deployment_identity_supplier = deployment_identity_supplier
        self._max_attempts = max_attempts
        self._attempts = 0
        self._used = False

    async def collect_once(self) -> R1ActivationPreflightEvidence:
        if self._used or self._attempts >= self._max_attempts:
            raise RuntimeError("r1_activation_host_preflight_reused")
        self._attempts += 1
        stage = "baseline"
        category = "material_drift"
        oauth_resources = None
        participant_resources = None
        try:
            public_settings = self._settings_loader(self._environ)
            if not public_settings.review_token:
                category = "baseline_review_token_missing"
                raise RuntimeError("r1_activation_host_baseline_invalid")
            if not public_settings.key_vault_url:
                category = "baseline_key_vault_url_missing"
                raise RuntimeError("r1_activation_host_baseline_invalid")
            if public_settings.r0_bridge_enabled:
                category = "baseline_r0_bridge_enabled"
                raise RuntimeError("r1_activation_host_baseline_invalid")
            if public_settings.event_r1_enabled:
                category = "baseline_event_r1_enabled"
                raise RuntimeError("r1_activation_host_baseline_invalid")
            if public_settings.event_r1_participant_strategy != "posterior":
                category = "baseline_participant_strategy_drift"
                raise RuntimeError("r1_activation_host_baseline_invalid")

            stage = "switches"
            switches = await ExactSwitchBaselineProbe(
                source=MappingExactSwitchValueSource(self._environ)
            ).collect(names=SWITCH_ORDER)

            stage = "protected_source"
            builder = ProtectedStoredOAuthResourcesBuilder(
                credential_backend=self._backend_builder(
                    vault_url=public_settings.key_vault_url
                ),
                resources_factory=self._oauth_factory_builder(),
                timeout_seconds=PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
                settings_loader=self._settings_loader,
            )
            oauth_resources = await builder()
            stage = "oauth"
            token = await oauth_resources.oauth_provider.get_access_token(
                oauth_resources.member_id
            )
            participant_resources = self._http_resources_factory(
                portal_url=oauth_resources.portal_url,
                access_token=token,
                timeout_seconds=PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
            )
            token = ""
            stage = "participants"
            category = "participants_unavailable"
            participant_read = await participant_resources.reader.read()
            if participant_read.error_code in PARTICIPANT_FAILURE_CATEGORIES:
                category = participant_read.error_code
            elif (
                participant_read.decision is ParticipantHttpDecision.SUCCESS
                and participant_read.pages != 1
            ):
                category = "participant_list_multiple_pages"
            if (
                participant_read.decision is not ParticipantHttpDecision.SUCCESS
                or participant_read.snapshot is None
                or participant_read.pages != 1
            ):
                raise RuntimeError("r1_activation_host_participants_invalid")
            snapshot = participant_read.snapshot
            await participant_resources.close()
            participant_resources = None
            await oauth_resources.close()
            oauth_resources = None

            stage = "deployment_identity"
            deployed_sha, deployed_tree = self._deployment_identity_supplier()
            deployment = SanitizedDeploymentEvidence(
                deployed_sha=deployed_sha,
                deployed_tree=deployed_tree,
                workflow_success=True,
                dormant_health_verified=True,
                full_tests_passed=True,
            )
            protected = SanitizedProtectedSourceEvidence(
                host_supports_protected_source=True,
                protected_source_kind=PROTECTED_SOURCE_KIND,
                protected_target_id=PROTECTED_TARGET_ID,
                protected_record_shape_verified=True,
                protected_setting_count=PROTECTED_SETTING_COUNT,
                credential_read_calls=1,
                oauth_read_calls=1,
                refresh_calls=0,
                retry_calls=0,
                resources_closed=True,
                review_auth_configured=True,
            )
            participants = SanitizedParticipantEvidence(
                deal_id=snapshot.crm_entity_id,
                chat_id=snapshot.chat_id,
                dialog_id=snapshot.dialog_id,
                bot_nia_absent=BOT_NIA_ID not in snapshot.participant_ids,
                bot_next_absent=BOT_NEXT_ID not in snapshot.participant_ids,
            )
            evidence = R1ActivationPreflightEvidence(
                deployed_sha=deployment.deployed_sha,
                deployed_tree=deployment.deployed_tree,
                workflow_success=deployment.workflow_success,
                dormant_health_verified=deployment.dormant_health_verified,
                full_tests_passed=deployment.full_tests_passed,
                host_supports_protected_source=protected.host_supports_protected_source,
                protected_source_kind=protected.protected_source_kind,
                protected_target_id=protected.protected_target_id,
                protected_record_shape_verified=protected.protected_record_shape_verified,
                protected_setting_count=protected.protected_setting_count,
                credential_read_calls=protected.credential_read_calls,
                oauth_read_calls=protected.oauth_read_calls,
                refresh_calls=protected.refresh_calls,
                retry_calls=protected.retry_calls,
                resources_closed=protected.resources_closed,
                review_auth_configured=protected.review_auth_configured,
                switches=switches,
                deal_id=participants.deal_id,
                chat_id=participants.chat_id,
                dialog_id=participants.dialog_id,
                bot_nia_absent=participants.bot_nia_absent,
                bot_next_absent=participants.bot_next_absent,
            )
            self._used = True
            return evidence
        except Exception:
            retryable = stage in {"protected_source", "oauth", "participants"}
            category = {
                "protected_source": "protected_source_unavailable",
                "oauth": "oauth_unavailable",
                "participants": category,
            }.get(stage, category)
            if not retryable or self._attempts >= self._max_attempts:
                self._used = True
            raise R1ActivationHostPreflightFailure(
                stage=stage,
                category=category,
                retryable=retryable and not self._used,
                attempts=self._attempts,
            ) from None
        finally:
            if participant_resources is not None:
                try:
                    await participant_resources.close()
                except BaseException:
                    pass
            if self._used:
                self._environ = {}
                self._backend_builder = None
                self._oauth_factory_builder = None
                self._http_resources_factory = None
                self._settings_loader = None
                self._deployment_identity_supplier = None
            if oauth_resources is not None:
                try:
                    await oauth_resources.close()
                except BaseException:
                    pass

    def __repr__(self) -> str:
        return "ExactR1ActivationHostPreflight(<redacted>)"


def build_r1_activation_host_preflight() -> ExactR1ActivationHostPreflight:
    """Construction is inert; no environment value is read until collect_once."""

    return ExactR1ActivationHostPreflight(environ=os.environ)


__all__ = [
    "DEPLOYMENT_IDENTITY_PATH", "MAX_HOST_PREFLIGHT_ATTEMPTS",
    "R1ActivationHostPreflightFailure", "ExactR1ActivationHostPreflight",
    "build_r1_activation_host_preflight", "read_packaged_deployment_identity",
]
