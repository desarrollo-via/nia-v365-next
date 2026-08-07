"""Auditoría M74 estática de los cuatro vínculos reales restantes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class M74RealLinkAudit:
    link: Literal[
        "nia_sender",
        "bitrix_sender",
        "exact_reply_deleter",
        "post_delete_history_reader",
    ]
    candidate: str
    candidate_method: str
    method_signature_matches: bool
    close_owner_identified: bool
    oauth_without_refresh_possible: bool
    call_budget: Literal[1] = 1
    retry_budget: Literal[0] = 0
    directly_compatible_with_m70_m71: Literal[False] = False
    missing_binding: str = ""

    def __post_init__(self) -> None:
        if not self.candidate or not self.candidate_method or not self.missing_binding:
            raise ValueError("m74_real_link_audit_invalid")


M74_REAL_LINKS = (
    M74RealLinkAudit(
        link="nia_sender",
        candidate="NiaClient",
        candidate_method="send_approved_text",
        method_signature_matches=True,
        close_owner_identified=True,
        oauth_without_refresh_possible=True,
        missing_binding="real_nia_sender_resource_factory_adapter",
    ),
    M74RealLinkAudit(
        link="bitrix_sender",
        candidate="BitrixClient",
        candidate_method="send_approved_message",
        method_signature_matches=True,
        close_owner_identified=True,
        oauth_without_refresh_possible=True,
        missing_binding="preloaded_token_bitrix_sender_resource_factory_adapter",
    ),
    M74RealLinkAudit(
        link="exact_reply_deleter",
        candidate="ReplyRollbackDeletePreview",
        candidate_method="delete_approved_reply",
        method_signature_matches=False,
        close_owner_identified=False,
        oauth_without_refresh_possible=False,
        missing_binding="exact_http_reply_deleter_and_resource_factory_adapter",
    ),
    M74RealLinkAudit(
        link="post_delete_history_reader",
        candidate="BitrixHistoryR0Client",
        candidate_method="get_session_history",
        method_signature_matches=False,
        close_owner_identified=True,
        oauth_without_refresh_possible=True,
        missing_binding="typed_history_to_rollback_mapping_resource_factory_adapter",
    ),
)


@dataclass(frozen=True)
class M74RealBindingAudit:
    phase: Literal["M74"] = "M74"
    state: Literal["NO-GO"] = "NO-GO"
    reason: str = "real_candidates_found_but_safe_factory_bindings_incomplete"
    links: tuple[M74RealLinkAudit, ...] = M74_REAL_LINKS
    real_link_count: Literal[4] = 4
    candidate_method_count: Literal[4] = 4
    directly_compatible_link_count: Literal[0] = 0
    missing_binding_count: Literal[4] = 4
    m70_m71_accept_fixture_resources_only: Literal[True] = True
    shared_stored_oauth_owner_required: Literal[True] = True
    stored_oauth_get_budget: Literal[1] = 1
    oauth_refresh_budget: Literal[0] = 0
    maximum_http_timeout_seconds: Literal[10] = 10
    every_resource_close_required: Literal[True] = True
    first_confirmation_request_ready: Literal[False] = False
    point_8_can_begin: Literal[False] = False
    human_attention_required_now: Literal[False] = False
    message_request_authorized: Literal[False] = False
    resources_constructed: Literal[False] = False
    source_bound: Literal[False] = False
    command_available: Literal[False] = False
    real_execution_authorized: Literal[False] = False
    external_calls: Literal[0] = 0
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False

    def __post_init__(self) -> None:
        expected = {
            "nia_sender",
            "bitrix_sender",
            "exact_reply_deleter",
            "post_delete_history_reader",
        }
        if (
            len(self.links) != self.real_link_count
            or {item.link for item in self.links} != expected
            or len({item.link for item in self.links}) != self.real_link_count
            or sum(item.directly_compatible_with_m70_m71 for item in self.links)
            != self.directly_compatible_link_count
            or sum(bool(item.missing_binding) for item in self.links)
            != self.missing_binding_count
            or any(item.call_budget != 1 or item.retry_budget != 0 for item in self.links)
        ):
            raise ValueError("m74_real_binding_audit_invalid")


def audit_real_bindings_after_m73() -> M74RealBindingAudit:
    """Devuelve un mapa fijo y redactado; no construye ni ejecuta recursos."""

    return M74RealBindingAudit()


__all__ = [
    "M74_REAL_LINKS",
    "M74RealBindingAudit",
    "M74RealLinkAudit",
    "audit_real_bindings_after_m73",
]
