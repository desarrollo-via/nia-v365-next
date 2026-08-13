"""One-shot allowlisted review-token bridge for the integral R1 EAOR."""

from __future__ import annotations

from pathlib import Path

from .r1_key_vault_protected_probe_dotenv_source import (
    EXPECTED_DOTENV_PATH,
    ExactReviewTokenDotenvSource,
)
from .r1_key_vault_protected_probe_invocation_owner import REVIEW_TOKEN_NAME
from .r1_remote_session_http_client import ExactR1RemoteSessionHttpClient


PUBLIC_ORIGIN = (
    "https://nia-v365-next-api-ekd4fza7e0fzevfd."
    "canadacentral-01.azurewebsites.net"
)


class ExactR1ReviewSessionClientFactory:
    """Opens only .env and only the exact review token, once."""

    __slots__ = ("_client_builder", "_dotenv_path", "_source_builder", "_used")

    def __init__(
        self,
        *,
        dotenv_path: Path = EXPECTED_DOTENV_PATH,
        source_builder=ExactReviewTokenDotenvSource,
        client_builder=ExactR1RemoteSessionHttpClient,
    ) -> None:
        if (
            not isinstance(dotenv_path, Path)
            or not callable(source_builder)
            or not callable(client_builder)
        ):
            raise TypeError("r1_review_session_dotenv_path_invalid")
        self._dotenv_path = dotenv_path
        self._source_builder = source_builder
        self._client_builder = client_builder
        self._used = False

    async def __call__(self) -> ExactR1RemoteSessionHttpClient:
        if self._used:
            raise RuntimeError("r1_review_session_factory_reused")
        self._used = True
        source_builder, self._source_builder = self._source_builder, None
        client_builder, self._client_builder = self._client_builder, None
        source = source_builder(self._dotenv_path)
        token = bytearray()
        try:
            await source.open()
            token = await source.read_exact(REVIEW_TOKEN_NAME)
            review_token = bytes(token).decode("utf-8")
            return client_builder(
                public_origin=PUBLIC_ORIGIN,
                review_token=review_token,
            )
        finally:
            review_token = ""
            token[:] = b"\x00" * len(token)
            token.clear()
            await source.close()

    def __repr__(self) -> str:
        return "ExactR1ReviewSessionClientFactory(<redacted>)"


__all__ = ["ExactR1ReviewSessionClientFactory", "PUBLIC_ORIGIN"]
