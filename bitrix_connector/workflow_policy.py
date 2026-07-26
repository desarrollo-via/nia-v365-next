"""Restricciones monotónicas del flujo operativo de cada evento."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from .modes import ConnectorMode


class WorkflowDecisionSource(str, Enum):
    HUMAN = "human"
    MODE_POLICY = "mode_policy"


class WorkflowInputAction(str, Enum):
    NEEDS_REVIEW = "needs_review"
    AUTO_APPROVE = "auto_approve"


class WorkflowOutputAction(str, Enum):
    NEEDS_REVIEW = "needs_review"
    AUTO_APPROVE = "auto_approve"
    SHADOW = "shadow"


class WorkflowGuard(BaseModel):
    """Un evento solo puede acumular restricciones, nunca perderlas."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    initial_mode: ConnectorMode
    observed_modes: tuple[ConnectorMode, ...]
    requires_input_approval: bool
    requires_output_approval: bool
    bitrix_send_allowed: bool

    @classmethod
    def from_mode(cls, mode: ConnectorMode) -> "WorkflowGuard":
        return cls(
            initial_mode=mode,
            observed_modes=(mode,),
            requires_input_approval=mode in {
                ConnectorMode.OFF,
                ConnectorMode.REVIEW,
            },
            requires_output_approval=mode in {
                ConnectorMode.OFF,
                ConnectorMode.REVIEW,
            },
            bitrix_send_allowed=mode in {
                ConnectorMode.REVIEW,
                ConnectorMode.ACTIVE,
            },
        )

    def observe(self, mode: ConnectorMode) -> "WorkflowGuard":
        """OFF pausa llamadas, pero no altera permanentemente el evento."""

        observed = self.observed_modes
        if not observed or observed[-1] is not mode:
            observed = (*observed, mode)
        return self.model_copy(
            update={
                "observed_modes": observed,
                "requires_input_approval": (
                    self.requires_input_approval
                    or mode is ConnectorMode.REVIEW
                ),
                "requires_output_approval": (
                    self.requires_output_approval
                    or mode is ConnectorMode.REVIEW
                ),
                "bitrix_send_allowed": (
                    self.bitrix_send_allowed
                    and mode is not ConnectorMode.SHADOW
                ),
            }
        )

    def input_action(self, *, preflight_ready: bool) -> WorkflowInputAction:
        if not preflight_ready or self.requires_input_approval:
            return WorkflowInputAction.NEEDS_REVIEW
        return WorkflowInputAction.AUTO_APPROVE

    def output_action(self, *, output_ready: bool) -> WorkflowOutputAction:
        if not self.bitrix_send_allowed:
            return WorkflowOutputAction.SHADOW
        if not output_ready or self.requires_output_approval:
            return WorkflowOutputAction.NEEDS_REVIEW
        return WorkflowOutputAction.AUTO_APPROVE

    @property
    def last_observed_mode(self) -> ConnectorMode:
        return self.observed_modes[-1]
