"""Dormant product binding for the persistent post-write host executor."""

from __future__ import annotations

from pathlib import Path

from .r1_post_write_close_host_executor import (
    PersistentHostCloseStore,
    R1PostWritePersistentHostExecutor,
)
from .r1_post_write_close_recovery import R1PostWriteSessionCloser


CHECKPOINT_PATH = Path(__file__).with_name(
    "r1_post_write_close_checkpoint.json"
)


class _LocalOwnerClient:
    __slots__ = ("_owner",)

    def __init__(self, owner) -> None:
        self._owner = owner

    async def status_once(self):
        return await self._owner.snapshot()

    async def disarm_once(self):
        return await self._owner.disarm_once()

    async def close(self) -> None:
        self._owner = None


async def _close_mounted_session_once() -> bool:
    # Lazy import avoids a router construction cycle and performs no I/O.
    from .router import event_scoped_r1_mount

    owner = event_scoped_r1_mount.owner
    if owner is None:
        return bool(
            event_scoped_r1_mount.state == "DORMANT"
            and not event_scoped_r1_mount.requested
            and not event_scoped_r1_mount.enabled
        )
    result = await R1PostWriteSessionCloser(
        client=_LocalOwnerClient(owner)
    ).close_once()
    return result.state == "VERIFIED-CLOSED" and result.resources_closed


def build_r1_post_write_persistent_host_executor(
) -> R1PostWritePersistentHostExecutor:
    """Construction is inert; effects begin only on authenticated invocation."""

    return R1PostWritePersistentHostExecutor(
        checkpoint_path=CHECKPOINT_PATH,
        store=PersistentHostCloseStore(),
        session_close=_close_mounted_session_once,
    )


__all__ = [
    "CHECKPOINT_PATH",
    "build_r1_post_write_persistent_host_executor",
]
