"""Configuración interactiva local de secretos OAuth sin mostrarlos."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import re
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key
from motor.motor_asyncio import AsyncIOMotorClient

from .config import load_settings
from .installation_factory import OAuthInstallationFactory
from .installation_status_factory import OAuthInstallationStatusFactory
from .oauth import MongoBitrixOAuthStore


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
MONGODB_SCHEMES = ("mongodb://", "mongodb+srv://")
CLIENT_ID_PATTERN = re.compile(r"^(?:local|app)\.[A-Za-z0-9._-]+$")


def _required_secret(prompt: str) -> str:
    value = getpass.getpass(prompt).strip()
    if not value:
        raise ValueError("required_secret_missing")
    return value


def _write_secret(name: str, value: str) -> None:
    if not ENV_PATH.is_file():
        raise RuntimeError("env_file_missing")
    set_key(str(ENV_PATH), name, value, quote_mode="always")


def configure_storage() -> int:
    mongo_uri = _required_secret("MongoDB Atlas URI (entrada oculta): ")
    if not mongo_uri.lower().startswith(MONGODB_SCHEMES):
        raise ValueError("mongodb_uri_scheme_invalid")
    mongo_db = input("Base Mongo exclusiva [nia]: ").strip() or "nia"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", mongo_db):
        raise ValueError("mongodb_database_name_invalid")
    _write_secret("NIA_BITRIX_MONGO_URI", mongo_uri)
    _write_secret("NIA_BITRIX_MONGO_DB", mongo_db)
    print("OK: almacenamiento OAuth configurado; no se mostró la URI.")
    return 0


def configure_client() -> int:
    client_id = _required_secret("Client ID de Bitrix (entrada oculta): ")
    if not CLIENT_ID_PATTERN.fullmatch(client_id):
        raise ValueError("bitrix_client_id_invalid")
    client_secret = _required_secret("Client secret de Bitrix (entrada oculta): ")
    _write_secret("NIA_BITRIX_CLIENT_ID", client_id)
    _write_secret("NIA_BITRIX_CLIENT_SECRET", client_secret)
    print("OK: credenciales de aplicación guardadas; no se mostraron.")
    return 0


def status() -> int:
    values = dotenv_values(ENV_PATH)
    safe = {
        "env_present": ENV_PATH.is_file(),
        "mongo_uri_present": bool(values.get("NIA_BITRIX_MONGO_URI")),
        "mongo_db_present": bool(values.get("NIA_BITRIX_MONGO_DB")),
        "client_id_present": bool(values.get("NIA_BITRIX_CLIENT_ID")),
        "client_secret_present": bool(values.get("NIA_BITRIX_CLIENT_SECRET")),
        "member_id_present": bool(values.get("NIA_BITRIX_MEMBER_ID")),
        "application_token_present": bool(
            values.get("NIA_BITRIX_APPLICATION_TOKEN")
        ),
        "mode": values.get("NIA_BITRIX_MODE") or "off",
        "installation_enabled": (
            values.get("NIA_BITRIX_INSTALLATION_ENABLED") or "false"
        ).lower()
        == "true",
        "pilot_enabled": (
            values.get("NIA_BITRIX_PILOT_ENABLED") or "false"
        ).lower()
        == "true",
        "pilot_emergency_stop": (
            values.get("NIA_BITRIX_PILOT_EMERGENCY_STOP") or "true"
        ).lower()
        == "true",
    }
    print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    return 0


async def _preflight_storage(
    factory: OAuthInstallationFactory | None = None,
) -> int:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    values.update(
        {
            "NIA_BITRIX_MODE": "off",
            "NIA_BITRIX_INSTALLATION_ENABLED": "true",
            "NIA_BITRIX_PILOT_ENABLED": "false",
            "NIA_BITRIX_PILOT_EMERGENCY_STOP": "true",
        }
    )
    settings = load_settings(values)
    resources = None
    try:
        resources = await (factory or OAuthInstallationFactory()).build(settings)
    except Exception:
        print("ERROR: oauth_storage_preflight_failed", file=sys.stderr)
        return 3
    finally:
        if resources is not None:
            await resources.close()
    print(
        json.dumps(
            {
                "connected": True,
                "installation_index_ready": True,
                "effective_mode": settings.effective_mode.value,
                "activation_locked": settings.activation_locked,
                "external_calls_enabled": settings.external_calls_enabled,
                "pilot_enabled": settings.pilot_enabled,
                "pilot_emergency_stop": settings.pilot_emergency_stop,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


async def _installation_status(
    factory: OAuthInstallationStatusFactory | None = None,
) -> int:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    settings = load_settings(values)
    resources = None
    try:
        resources = await (
            factory or OAuthInstallationStatusFactory()
        ).build(settings)
        result = await resources.service.get_status(
            settings.bitrix_domain or ""
        )
    except Exception as exc:
        fields = getattr(exc, "fields", ())
        safe_fields = ",".join(
            str(field)
            for field in fields
            if str(field)
            in {
                "member_id",
                "domain",
                "client_endpoint",
                "server_endpoint",
                "access_token",
                "refresh_token",
                "application_token",
                "expires_at",
                "updated_at",
                "revision",
            }
        )
        print(
            "ERROR: oauth_installation_status_failed"
            f" type={type(exc).__name__}"
            f" fields={safe_fields or 'none'}",
            file=sys.stderr,
        )
        return 4
    finally:
        if resources is not None:
            await resources.close()
    print(result.model_dump_json())
    return 0


async def _sync_installation_identity(store=None) -> int:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    settings = load_settings(values)
    client = None
    try:
        selected_store = store
        if selected_store is None:
            if not settings.mongo_uri or not settings.mongo_db:
                raise RuntimeError("oauth_storage_not_configured")
            client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
            collection = client[settings.mongo_db][
                settings.installations_collection
            ]
            selected_store = MongoBitrixOAuthStore(collection)
        installation = await selected_store.get_installation_by_domain(
            settings.bitrix_domain or ""
        )
        if installation is None:
            raise RuntimeError("oauth_installation_not_found")
        _write_secret("NIA_BITRIX_MEMBER_ID", installation.member_id)
        _write_secret(
            "NIA_BITRIX_APPLICATION_TOKEN",
            installation.application_token.get_secret_value(),
        )
    except Exception:
        print("ERROR: oauth_identity_sync_failed", file=sys.stderr)
        return 5
    finally:
        if client is not None:
            client.close()
    print(
        json.dumps(
            {
                "member_id_saved": True,
                "application_token_saved": True,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configura secretos locales de OAuth sin imprimirlos."
    )
    parser.add_argument(
        "command",
        choices=(
            "configure-storage",
            "configure-client",
            "status",
            "preflight-storage",
            "installation-status",
            "sync-installation-identity",
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "configure-storage":
            return configure_storage()
        if args.command == "configure-client":
            return configure_client()
        if args.command == "preflight-storage":
            return asyncio.run(_preflight_storage())
        if args.command == "installation-status":
            return asyncio.run(_installation_status())
        if args.command == "sync-installation-identity":
            return asyncio.run(_sync_installation_identity())
        return status()
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
