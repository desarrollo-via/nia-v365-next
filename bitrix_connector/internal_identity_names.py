"""Nombres humanos estables para identidades tecnicas de Bitrix.

Los nombres son solo una convencion interna de lectura. Los identificadores
tecnicos siguen siendo la autoridad para validaciones y operaciones.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


BOT_HUMAN_NAMES: Mapping[int, str] = MappingProxyType({
    245339: "Bot NIA",
    373259: "Bot Next",
})

CHAT_HUMAN_NAMES: Mapping[int, str] = MappingProxyType({
    78733: "Chat Test",
})


def _positive_identifier(value: int, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def human_bot_name(bot_id: int) -> str:
    """Devuelve el nombre interno o hace visible que falta catalogarlo."""
    bot_id = _positive_identifier(bot_id, "bot_id")
    return BOT_HUMAN_NAMES.get(bot_id, f"Bot no catalogado {bot_id}")


def human_chat_name(chat_id: int) -> str:
    """Devuelve el nombre interno o hace visible que falta catalogarlo."""
    chat_id = _positive_identifier(chat_id, "chat_id")
    return CHAT_HUMAN_NAMES.get(chat_id, f"Chat no catalogado {chat_id}")


def bot_identity_label(bot_id: int) -> str:
    """Etiqueta legible que conserva el identificador operativo exacto."""
    bot_id = _positive_identifier(bot_id, "bot_id")
    return f"{human_bot_name(bot_id)} (bot_id={bot_id})"


def chat_identity_label(chat_id: int) -> str:
    """Etiqueta legible que conserva chat_id y dialog_id exactos."""
    chat_id = _positive_identifier(chat_id, "chat_id")
    return (
        f"{human_chat_name(chat_id)} "
        f"(chat_id={chat_id}, dialog_id=chat{chat_id})"
    )


__all__ = [
    "BOT_HUMAN_NAMES",
    "CHAT_HUMAN_NAMES",
    "bot_identity_label",
    "chat_identity_label",
    "human_bot_name",
    "human_chat_name",
]
