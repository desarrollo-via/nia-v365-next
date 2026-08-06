"""Literal M86-AO categórico, preparado pero no mostrado."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


M86AO_AUTHORIZATION_LITERAL = (
    "AUTORIZACIÓN SONDA M86-AO — UNA SOLA LECTURA CATEGÓRICA: Autorizo "
    "exclusivamente una única tentativa agregada sobre las siete claves exactas "
    "del entorno del proceso: "
    + ", ".join(PROTECTED_SETTING_NAMES)
    + ". Autorizo leerlas una sola vez sin enumerar el entorno, transferir sólo "
    "buffers mutables en memoria y comprobar presencia agregada y FIT del "
    "candidato M84 dentro del máximo de 2560 bytes. Autorizo como única salida "
    "pública FIT/none o NO-GO acompañado exclusivamente por una de estas "
    "categorías agregadas: authorization_invalid, source_aggregate_unavailable, "
    "candidate_not_fit, composition_failed o cleanup_ambiguous. No autorizo "
    "mostrar, copiar, transcribir, contar, medir, inferir ni registrar valores, "
    "longitudes, claves individuales, progreso o número de lecturas; todos los "
    "buffers y recursos deben limpiarse y cerrarse en finally. No autorizo "
    "fallback, .env, App Settings, Credential Manager, escrituras, OAuth, Mongo, "
    "red, Bitrix, NIA, historial, mensajes, reintentos ni cambios productivos. "
    "Cualquier deriva o cierre ambiguo consume la autorización y termina en "
    "NO-GO con la categoría de cierre allowlisted."
)


@dataclass(frozen=True)
class M86AOAuthorizationContract:
    phase: Literal["M86-AO"] = "M86-AO"
    state: Literal["PREPARED-NOT-SHOWN"] = "PREPARED-NOT-SHOWN"
    exact_literal: str = M86AO_AUTHORIZATION_LITERAL
    shown_to_person: Literal[False] = False
    authorization_received: Literal[False] = False
    current_real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0

    def accepts(self, candidate: str) -> bool:
        return type(candidate) is str and candidate == self.exact_literal


__all__ = ["M86AO_AUTHORIZATION_LITERAL", "M86AOAuthorizationContract"]
