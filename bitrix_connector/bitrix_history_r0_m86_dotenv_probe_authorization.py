"""Autorización M86-BD para dotenv, preparada pero no mostrada ni enlazada."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


M86BD_PUBLIC_CATEGORIES = (
    "authorization_invalid",
    "source_open_unavailable",
    "source_transfer_unavailable",
    "candidate_not_fit",
    "composition_failed",
    "cleanup_ambiguous",
)

M86BD_AUTHORIZATION_LITERAL = (
    "AUTORIZACIÓN SONDA M86-BD — UNA ÚNICA APERTURA PROTEGIDA DE .env: "
    "Autorizo exclusivamente una única tentativa de apertura del archivo .env "
    "ubicado en el PROJECT_ROOT de nia-next, sin enumerar rutas ni fuentes, para "
    "leer sólo estas siete claves exactas: "
    + ", ".join(PROTECTED_SETTING_NAMES)
    + ". Autorizo transferir sus valores únicamente como buffers mutables en "
    "memoria mediante M86-BC y M86-AZ, comprobar presencia agregada y FIT del "
    "candidato M84 dentro del máximo de 2560 bytes, y limpiar y cerrar todos los "
    "buffers y recursos en finally. Autorizo como única salida pública FIT/none "
    "o NO-GO acompañado exclusivamente por una de estas categorías agregadas: "
    + ", ".join(M86BD_PUBLIC_CATEGORIES[:-1])
    + " o "
    + M86BD_PUBLIC_CATEGORIES[-1]
    + ". No autorizo mostrar, copiar, transcribir, contar, medir, inferir ni "
    "registrar valores, longitudes, estados individuales, progreso o detalles "
    "de ruta. No autorizo fallback, enumeración, App Settings, Credential "
    "Manager, entorno del proceso, OAuth, Mongo, red, Bitrix, NIA, historial, "
    "mensajes, escrituras, borrados, reintentos ni cambios productivos. Cualquier "
    "deriva o cierre ambiguo consume la autorización y termina en "
    "NO-GO/cleanup_ambiguous cuando corresponda."
)


@dataclass(frozen=True)
class M86BDAuthorizationContract:
    phase: Literal["M86-BD"] = "M86-BD"
    state: Literal["PREPARED-NOT-SHOWN"] = "PREPARED-NOT-SHOWN"
    exact_literal: str = M86BD_AUTHORIZATION_LITERAL
    shown_to_person: Literal[False] = False
    authorization_received: Literal[False] = False
    linked_to_execution: Literal[False] = False
    single_open_budget: Literal[0] = 0
    current_real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0

    def accepts(self, candidate: str) -> bool:
        return type(candidate) is str and candidate == self.exact_literal


__all__ = [
    "M86BD_AUTHORIZATION_LITERAL",
    "M86BD_PUBLIC_CATEGORIES",
    "M86BDAuthorizationContract",
]
