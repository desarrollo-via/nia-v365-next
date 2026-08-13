"""Sanitized, non-persistent payload for one future R1 host-side probe."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
from collections.abc import Callable, Mapping


SCHEMA = "nia-next-r1-host-probe-v1"
SETTING_NAME = "NIA_BITRIX_KEY_VAULT_URL"
EXPECTED_DISTRIBUTIONS = (
    ("azure-identity", "1.25.3"),
    ("azure-keyvault-secrets", "4.11.0"),
    ("aiohttp", "3.14.3"),
)
_VAULT_URL = re.compile(
    r"https://[a-z0-9](?:[a-z0-9-]{1,22}[a-z0-9])?\.vault\.azure\.net"
)


def collect_sanitized(
    *,
    environ: Mapping[str, str],
    version_reader: Callable[[str], str],
) -> dict[str, object]:
    """Read only three distributions and one exact environment subscription."""

    if environ is None or not callable(getattr(environ, "__getitem__", None)):
        raise TypeError("r1_host_probe_environment_invalid")
    if not callable(version_reader):
        raise TypeError("r1_host_probe_version_reader_invalid")

    versions: dict[str, str] = {}
    for distribution, expected in EXPECTED_DISTRIBUTIONS:
        try:
            actual = version_reader(distribution)
        except Exception:
            raise RuntimeError("r1_host_probe_package_unavailable") from None
        if type(actual) is not str or actual != expected:
            raise RuntimeError("r1_host_probe_package_version_mismatch")
        versions[distribution] = actual

    try:
        setting_value = environ[SETTING_NAME]
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
            raise RuntimeError("r1_host_probe_setting_invalid")

    return {
        "schema": SCHEMA,
        "packages": versions,
        "setting_present": setting_present,
        "setting_valid": setting_valid,
        "external_calls": 0,
        "writes": 0,
    }


def main() -> int:
    evidence = collect_sanitized(
        environ=os.environ,
        version_reader=importlib.metadata.version,
    )
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
