"""Dormant composition for the post-write R1 safety closer.

Construction and preview are local-only.  Surface builders are invoked only
after the exact consumed-write ledger has been verified, and building the
coordinator does not execute any closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .r1_post_write_close_recovery import (
    R1PostWriteActivationCloser,
    R1PostWriteCloseRecovery,
    R1PostWriteKeyVaultCloser,
    R1PostWriteSessionCloser,
    verify_consumed_write_checkpoint,
)


@dataclass(frozen=True)
class R1PostWriteCloseBindingPreview:
    state: Literal["DORMANT", "BOUND-DORMANT", "NO-GO-CHECKPOINT"]
    checkpoint_verified: bool
    builder_calls: Literal[0] = 0
    close_calls: Literal[0] = 0
    messages_sent: Literal[0] = 0
    secret_write_calls: Literal[0] = 0
    resume_calls: Literal[0] = 0
    external_calls: Literal[0] = 0


class R1PostWriteCloseDormantRealBinding:
    """Lazily composes exact closure surfaces behind a local checkpoint."""

    __slots__ = (
        "_activation_control_builder", "_built", "_checkpoint_failed",
        "_key_vault_verifier_builder", "_ledger_path",
        "_session_client_builder",
    )

    def __init__(
        self,
        *,
        ledger_path: Path,
        session_client_builder: Callable[[], object],
        activation_control_builder: Callable[[], object],
        key_vault_verifier_builder: Callable[[], object],
    ) -> None:
        if (
            not isinstance(ledger_path, Path)
            or not all(callable(item) for item in (
                session_client_builder,
                activation_control_builder,
                key_vault_verifier_builder,
            ))
        ):
            raise TypeError("r1_post_write_close_binding_dependency_invalid")
        self._ledger_path = ledger_path
        self._session_client_builder = session_client_builder
        self._activation_control_builder = activation_control_builder
        self._key_vault_verifier_builder = key_vault_verifier_builder
        self._built = False
        self._checkpoint_failed = False

    def preview(self) -> R1PostWriteCloseBindingPreview:
        if self._checkpoint_failed:
            state = "NO-GO-CHECKPOINT"
        else:
            state = "BOUND-DORMANT" if self._built else "DORMANT"
        return R1PostWriteCloseBindingPreview(
            state=state,
            checkpoint_verified=self._built,
        )

    def build_recovery_once(self) -> R1PostWriteCloseRecovery:
        if self._built or self._checkpoint_failed:
            raise RuntimeError("r1_post_write_close_binding_reused")
        if not verify_consumed_write_checkpoint(self._ledger_path):
            self._checkpoint_failed = True
            raise RuntimeError("r1_post_write_close_checkpoint_invalid")

        session_builder = self._session_client_builder
        activation_builder = self._activation_control_builder
        key_vault_builder = self._key_vault_verifier_builder

        async def close_session():
            return await R1PostWriteSessionCloser(
                client=session_builder()
            ).close_once()

        async def close_activation():
            return await R1PostWriteActivationCloser(
                control=activation_builder()
            ).close_once()

        async def close_key_vault():
            return await R1PostWriteKeyVaultCloser(
                verifier=key_vault_builder()
            ).close_once()

        # The coordinator is still dormant: factories are materialized only
        # inside their corresponding close operation.
        self._built = True
        return R1PostWriteCloseRecovery(
            ledger_path=self._ledger_path,
            session_close=close_session,
            activation_close=close_activation,
            key_vault_close=close_key_vault,
        )

    def __repr__(self) -> str:
        return "R1PostWriteCloseDormantRealBinding(<redacted>)"


__all__ = [
    "R1PostWriteCloseBindingPreview",
    "R1PostWriteCloseDormantRealBinding",
]
