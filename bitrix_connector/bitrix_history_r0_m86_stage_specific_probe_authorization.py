"""Literal M86-AU por etapa, preparado pero no mostrado."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


M86AU_PUBLIC_CATEGORIES = (
    "authorization_invalid",
    "source_factory_unavailable",
    "source_open_unavailable",
    "source_transfer_unavailable",
    "candidate_not_fit",
    "composition_failed",
    "cleanup_ambiguous",
)

M86AU_AUTHORIZATION_LITERAL = (
    "AUTORIZACIÓN SONDA M86-AU — UNA SOLA LECTURA CATEGÓRICA POR ETAPA: "
    "Autorizo exclusivamente una única tentativa agregada sobre las siete "
    "claves exactas del entorno del proceso: "
    + ", ".join(PROTECTED_SETTING_NAMES)
    + ". Autorizo leerlas una sola vez sin enumerar el entorno, transferir sólo "
    "buffers mutables en memoria y comprobar presencia agregada y FIT del "
    "candidato M84 dentro del máximo de 2560 bytes. Autorizo como única salida "
    "pública FIT/none o NO-GO acompañado exclusivamente por una de estas "
    "categorías agregadas por etapa: "
    + ", ".join(M86AU_PUBLIC_CATEGORIES[:-1])
    + " o "
    + M86AU_PUBLIC_CATEGORIES[-1]
    + ". No autorizo mostrar, copiar, transcribir, contar, medir, inferir ni "
    "registrar valores, longitudes, claves individuales, progreso o número de "
    "lecturas; todos los buffers y recursos deben limpiarse y cerrarse en "
    "finally. No autorizo fallback, .env, App Settings, Credential Manager, "
    "escrituras, OAuth, Mongo, red, Bitrix, NIA, historial, mensajes, reintentos "
    "ni cambios productivos. Cualquier deriva o cierre ambiguo consume la "
    "autorización y termina en NO-GO con la categoría de cierre allowlisted."
)


@dataclass(frozen=True)
class M86AUAuthorizationContract:
    phase: Literal["M86-AU"] = "M86-AU"
    state: Literal["PREPARED-NOT-SHOWN"] = "PREPARED-NOT-SHOWN"
    exact_literal: str = M86AU_AUTHORIZATION_LITERAL
    shown_to_person: Literal[False] = False
    authorization_received: Literal[False] = False
    linked_to_execution: Literal[False] = False
    current_real_read_budget: Literal[0] = 0
    external_calls: Literal[0] = 0

    def accepts(self, candidate: str) -> bool:
        return type(candidate) is str and candidate == self.exact_literal


__all__ = [
    "M86AU_AUTHORIZATION_LITERAL",
    "M86AU_PUBLIC_CATEGORIES",
    "M86AUAuthorizationContract",
]
