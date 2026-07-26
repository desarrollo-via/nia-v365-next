"""Diagnóstico OAuth de solo lectura, sin exponer identidades ni secretos."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Literal, Optional, Protocol

from pydantic import BaseModel, ValidationError

from .oauth import BitrixOAuthInstallation


OAUTH_INSTALLATION_DIAGNOSTIC_FIELDS = frozenset(
    {
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


class OAuthInstallationStatusResponse(BaseModel):
    status: Literal["installed", "not_found"]
    installation_present: bool
    access_token_present: bool
    refresh_token_present: bool
    application_token_present: bool
    revision: Optional[int] = None
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class OAuthInstallationStatusStore(Protocol):
    async def get_installation_by_domain(
        self,
        domain: str,
    ) -> Optional[BitrixOAuthInstallation]: ...


class OAuthInstallationStatusStorageUnavailable(RuntimeError):
    """La consulta al almacén no pudo completarse."""


class OAuthInstallationStatusStoredDocumentInvalid(RuntimeError):
    """El documento encontrado no cumple el contrato OAuth persistido."""

    stage = "document_validation"

    def __init__(self, fields: Iterable[str] = ()) -> None:
        super().__init__("stored_oauth_installation_invalid")
        self.fields = tuple(
            sorted(
                {
                    field
                    for field in fields
                    if field in OAUTH_INSTALLATION_DIAGNOSTIC_FIELDS
                }
            )
        )


def _validation_fields(error: ValidationError) -> tuple[str, ...]:
    fields = []
    for issue in error.errors(include_url=False, include_context=False):
        location = issue.get("loc", ())
        if location and isinstance(location[0], str):
            fields.append(location[0])
    return tuple(fields)


class OAuthInstallationStatusService:
    def __init__(self, store: OAuthInstallationStatusStore) -> None:
        self._store = store

    async def get_status(self, domain: str) -> OAuthInstallationStatusResponse:
        try:
            installation = await self._store.get_installation_by_domain(domain)
        except ValidationError as exc:
            raise OAuthInstallationStatusStoredDocumentInvalid(
                _validation_fields(exc)
            ) from exc
        except Exception as exc:
            raise OAuthInstallationStatusStorageUnavailable(
                "oauth_installation_storage_unavailable"
            ) from exc
        if installation is None:
            return OAuthInstallationStatusResponse(
                status="not_found",
                installation_present=False,
                access_token_present=False,
                refresh_token_present=False,
                application_token_present=False,
            )

        return OAuthInstallationStatusResponse(
            status="installed",
            installation_present=True,
            access_token_present=bool(
                installation.access_token.get_secret_value().strip()
            ),
            refresh_token_present=bool(
                installation.refresh_token.get_secret_value().strip()
            ),
            application_token_present=bool(
                installation.application_token.get_secret_value().strip()
            ),
            revision=installation.revision,
            updated_at=installation.updated_at,
            expires_at=installation.expires_at,
        )
