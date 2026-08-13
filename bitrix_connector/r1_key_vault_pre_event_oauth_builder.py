"""Linux pre-event lease backed by one exact Managed Identity secret read."""

from __future__ import annotations

import time
from collections.abc import Callable

from .bitrix_event_scoped_r1_pre_event_oauth_adapter import (
    DormantStoredOAuthPreEventLeaseFactory,
)
from .bitrix_event_scoped_r1_protected_oauth_builder import (
    PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    ProtectedStoredOAuthResourcesBuilder,
)
from .controlled_chat_participant_adapter import ParticipantSafetyState
from .controlled_chat_participant_http import ControlledParticipantHttpResources
from .pilot_discovery_factory import PilotDiscoveryOAuthFactory
from .r1_key_vault_exact_secret_backend import (
    build_managed_identity_exact_secret_backend,
)


def build_dormant_key_vault_pre_event_lease_factory(
    *,
    safety: ParticipantSafetyState,
    vault_url: str,
    timeout_seconds: float = PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    protected_backend_builder=build_managed_identity_exact_secret_backend,
    resources_factory_builder=PilotDiscoveryOAuthFactory,
    http_resources_factory=ControlledParticipantHttpResources.build,
) -> DormantStoredOAuthPreEventLeaseFactory:
    """Bind the exact vault lazily; construction performs no protected read."""

    if not callable(protected_backend_builder) or not callable(
        resources_factory_builder
    ):
        raise TypeError("pre_event_key_vault_binding_invalid")
    builder = ProtectedStoredOAuthResourcesBuilder(
        credential_backend=protected_backend_builder(vault_url=vault_url),
        resources_factory=resources_factory_builder(),
        timeout_seconds=timeout_seconds,
    )
    return DormantStoredOAuthPreEventLeaseFactory(
        safety=safety,
        resources_builder=builder,
        timeout_seconds=timeout_seconds,
        clock=clock,
        http_resources_factory=http_resources_factory,
    )


__all__ = ["build_dormant_key_vault_pre_event_lease_factory"]
