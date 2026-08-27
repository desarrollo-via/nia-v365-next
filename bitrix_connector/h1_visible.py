"""Compatibilidad del conector con el visor H1 neutro."""

from h1_visible import (
    H1_BOT_ID,
    H1_CHAT_ID,
    H1_DIALOG_IDS,
    H1_ROUTE,
    H1_TTL_SECONDS,
    H1VisibleBuffer,
    H1VisibleRecord,
    create_h1_visible_router,
    h1_visible_buffer,
)

__all__ = [
    "H1_BOT_ID", "H1_CHAT_ID", "H1_DIALOG_IDS", "H1_ROUTE", "H1_TTL_SECONDS",
    "H1VisibleBuffer", "H1VisibleRecord", "create_h1_visible_router", "h1_visible_buffer",
]
