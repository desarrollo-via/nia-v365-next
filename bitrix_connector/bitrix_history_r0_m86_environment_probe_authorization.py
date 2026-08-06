"""Literal M86-AF: autorización futura; no contiene ruta ejecutable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES


M86AF_AUTHORIZATION_LITERAL = (
    "AUTORIZACIÓN SONDA M86-AF — UNA SOLA LECTURA: Autorizo exclusivamente "
    "una única tentativa agregada sobre las siete claves exactas del entorno "
    "del proceso: "
    + ", ".join(PROTECTED_SETTING_NAMES)
    + ". Autorizo leerlas una sola vez sin enumerar el entorno, transferir sólo "
    "buffers mutables en memoria y comprobar únicamente presencia agregada y "
    "FIT del candidato M84 dentro del máximo de 2560 bytes, sin mostrar, copiar, "
    "transcribir, contar, medir ni registrar valores, longitudes o estados "
    "individuales; todos los buffers y recursos deben limpiarse y cerrarse en "
    "finally. Autorizo sólo una salida pública categórica FIT o NO-GO. No "
    "autorizo fallback, .env, App Settings, Credential Manager, escrituras, "
    "OAuth, Mongo, red, Bitrix, NIA, historial, mensajes, reintentos ni cambios "
    "productivos. Cualquier deriva o cierre ambiguo consume la autorización y "
    "termina en NO-GO."
)


@dataclass(frozen=True)
class M86AFAuthorizationContract:
    phase: Literal["M86-AF"] = "M86-AF"
    state: Literal["PREPARED-NOT-EXECUTABLE"] = "PREPARED-NOT-EXECUTABLE"
    exact_literal: str = M86AF_AUTHORIZATION_LITERAL
    exact_key_count: Literal[7] = 7
    execution_surface_present: Literal[False] = False
    authorization_received: Literal[False] = False
    values_read: Literal[False] = False
    external_calls: Literal[0] = 0

    def accepts(self, candidate: str) -> bool:
        return type(candidate) is str and candidate == self.exact_literal


__all__ = ["M86AF_AUTHORIZATION_LITERAL", "M86AFAuthorizationContract"]
