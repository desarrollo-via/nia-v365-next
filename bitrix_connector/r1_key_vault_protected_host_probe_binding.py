"""Lazy production binding for the protected R1 host probe."""

from __future__ import annotations

import importlib.metadata
import os

from .r1_key_vault_protected_host_probe import ExactOneShotProtectedHostProbe


def build_protected_host_probe() -> ExactOneShotProtectedHostProbe:
    """Bind readers without collecting environment or package evidence."""

    return ExactOneShotProtectedHostProbe(
        environ=os.environ,
        version_reader=importlib.metadata.version,
    )


__all__ = ["build_protected_host_probe"]
