"""Dormant, exact and sanitized host probe for the protected Review route."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field


SETTING_NAME = "NIA_BITRIX_KEY_VAULT_URL"
EXPECTED_DISTRIBUTIONS = (
    ("azure-identity", "1.25.3"),
    ("azure-keyvault-secrets", "4.11.0"),
    ("aiohttp", "3.14.3"),
)
_VAULT_URL = re.compile(
    r"https://[a-z0-9](?:[a-z0-9-]{1,22}[a-z0-9])?\.vault\.azure\.net"
)


class SanitizedHostProbePackages(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    azure_identity: Literal["1.25.3"] = Field(alias="azure-identity")
    azure_keyvault_secrets: Literal["4.11.0"] = Field(
        alias="azure-keyvault-secrets"
    )
    aiohttp: Literal["3.14.3"]


class SanitizedProtectedHostProbeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_name: Literal["nia-next-r1-host-probe-v1"] = Field(alias="schema")
    packages: SanitizedHostProbePackages
    setting_present: bool
    setting_valid: Optional[bool]
    external_calls: Literal[0] = 0
    writes: Literal[0] = 0


class ProtectedHostProbeReader(Protocol):
    def collect_once(self) -> SanitizedProtectedHostProbeEvidence: ...


class ExactOneShotProtectedHostProbe:
    """Reads nothing at construction and consumes one authenticated collection."""

    __slots__ = ("_environ", "_used", "_version_reader")

    def __init__(
        self,
        *,
        environ: Mapping[str, str],
        version_reader: Callable[[str], str],
    ) -> None:
        if environ is None or not callable(getattr(environ, "__getitem__", None)):
            raise TypeError("r1_protected_host_probe_environment_invalid")
        if not callable(version_reader):
            raise TypeError("r1_protected_host_probe_version_reader_invalid")
        self._environ = environ
        self._version_reader = version_reader
        self._used = False

    def collect_once(self) -> SanitizedProtectedHostProbeEvidence:
        if self._used:
            raise RuntimeError("r1_protected_host_probe_already_consumed")
        self._used = True

        versions: dict[str, str] = {}
        for distribution, expected in EXPECTED_DISTRIBUTIONS:
            try:
                actual = self._version_reader(distribution)
            except Exception:
                raise RuntimeError(
                    "r1_protected_host_probe_package_unavailable"
                ) from None
            if type(actual) is not str or actual != expected:
                raise RuntimeError(
                    "r1_protected_host_probe_package_version_mismatch"
                )
            versions[distribution] = actual

        try:
            setting_value = self._environ[SETTING_NAME]
        except KeyError:
            setting_present = False
            setting_valid = None
        else:
            setting_present = True
            setting_valid = (
                type(setting_value) is str
                and _VAULT_URL.fullmatch(setting_value) is not None
            )
            if not setting_valid:
                raise RuntimeError("r1_protected_host_probe_setting_invalid")

        return SanitizedProtectedHostProbeEvidence(
            schema="nia-next-r1-host-probe-v1",
            packages=SanitizedHostProbePackages(**versions),
            setting_present=setting_present,
            setting_valid=setting_valid,
            external_calls=0,
            writes=0,
        )


__all__ = [
    "ExactOneShotProtectedHostProbe",
    "ProtectedHostProbeReader",
    "SanitizedProtectedHostProbeEvidence",
]

