"""Literales M63 y parser M66 one-shot, inyectable y sin fuente real."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from .bitrix_history_r0_dormant_confirmation_coordinator import (
    FIRST_CONFIRMATION_SCOPE,
    MANUAL_REMOVAL_SCOPE,
    SECOND_CONFIRMATION_SCOPE,
    InjectedConfirmation,
    InjectedManualRemovalEvidence,
)


M63_FIRST_CONFIRMATION_TEXT = (
    "PRIMERA CONFIRMACIÓN R1 — PREFLIGHT Y PREPARACIÓN: Autorizo exclusivamente "
    "preparar una única prueba sobre chat_id=78733, dialog_id=chat78733 y bot "
    "373259, con una eventual respuesta Bitrix y rollback exacto limitado al ID "
    "devuelto por ese envío. Autorizo una sola apertura interna protegida de "
    "C:\\Users\\H\\Desktop\\f\\web\\phyton-codigo\\nia-next\\.env para transferir "
    "únicamente NIA_BITRIX_DOMAIN, NIA_BITRIX_MEMBER_ID, NIA_BITRIX_CLIENT_ID, "
    "NIA_BITRIX_CLIENT_SECRET, NIA_BITRIX_MONGO_URI, NIA_BITRIX_MONGO_DB y "
    "NIA_BITRIX_INSTALLATIONS_COLLECTION, sin mostrar ni registrar valores; "
    "obtener una vez el OAuth almacenado sin renovarlo; y ejecutar como máximo "
    "una lectura de imbot.v2.Revision.get, imbot.v2.Bot.list, "
    "imopenlines.config.get para Línea 13 e imopenlines.dialog.get para "
    "chat78733. No autorizo historial, llamada NIA, envío, borrado, otro mensaje, "
    "reintento ni cambio productivo. Cualquier deriva o cierre ambiguo consume "
    "la autorización y termina en NO-GO."
)

M63_MANUAL_REMOVAL_TEXT = (
    "CONFIRMO QUE RETIRÉ MANUALMENTE A NIA 245339 DEL CHAT CONTROLADO Y LA "
    "MANTENDRÉ FUERA DURANTE ESTA PRUEBA."
)

M63_SECOND_CONFIRMATION_TEXT = (
    "SEGUNDA CONFIRMACIÓN R1 — EJECUCIÓN INMEDIATA: Confirmo que el preflight R1 "
    "exacto terminó READY sin deriva y autorizo una sola ejecución de máximo 180 "
    "segundos, sin reintentos, únicamente para chat_id=78733, "
    "dialog_id=chat78733, sesión derivada de ese diálogo y bot 373259. Autorizo "
    "pedir un único mensaje humano cuando el lector muestre WAITING-MESSAGE, "
    "realizar como máximo una lectura de imopenlines.session.history.get para "
    "identificar un solo mensaje posterior al ancla, una llamada a NIA Next con "
    "ese texto, un envío imbot.v2.Chat.Message.send de la respuesta al mismo "
    "diálogo y una relectura de historial para verificar el ID recibido. Si "
    "existe ID de envío y falla cualquier verificación posterior, autorizo como "
    "rollback una sola llamada imbot.v2.Chat.Message.delete con botId=373259, "
    "messageId derivado exclusivamente del recibo y complete=true, seguida de "
    "una sola relectura de la misma sesión para verificar su ausencia. No "
    "autorizo otros chats, persistencia, renovación OAuth, cambios de Línea 13, "
    "bots, Wazzup, rutas, asignaciones o vinculaciones. Cualquier ambigüedad "
    "detiene, cierra recursos y consume esta autorización."
)


InjectedTextReader = Callable[[], Awaitable[str]]


class OneShotM63LiteralParser:
    """Consume exactamente tres literales, en orden, y luego se inutiliza."""

    def __init__(self, *, text_reader: InjectedTextReader) -> None:
        if not callable(text_reader):
            raise TypeError("m63_literal_reader_invalid")
        self._reader: Optional[InjectedTextReader] = text_reader
        self._stage = 0

    async def _read_exact(self, *, stage: int, expected: str) -> None:
        reader = self._reader
        if reader is None or self._stage != stage:
            self._clear()
            raise RuntimeError("m63_literal_order_or_reuse_invalid")
        try:
            value = await reader()
            if type(value) is not str or value != expected:
                raise ValueError("m63_literal_mismatch")
            self._stage += 1
        except BaseException:
            self._clear()
            raise

    def _clear(self) -> None:
        self._reader = None
        self._stage = -1

    def clear(self) -> None:
        """Permite al owner exterior limpiar aunque la secuencia quede parcial."""

        self._clear()

    async def read_first_confirmation(self) -> InjectedConfirmation:
        await self._read_exact(stage=0, expected=M63_FIRST_CONFIRMATION_TEXT)
        return InjectedConfirmation(True, FIRST_CONFIRMATION_SCOPE)

    async def read_manual_evidence(self) -> InjectedManualRemovalEvidence:
        await self._read_exact(stage=1, expected=M63_MANUAL_REMOVAL_TEXT)
        return InjectedManualRemovalEvidence(True, MANUAL_REMOVAL_SCOPE)

    async def read_second_confirmation(self) -> InjectedConfirmation:
        await self._read_exact(stage=2, expected=M63_SECOND_CONFIRMATION_TEXT)
        result = InjectedConfirmation(True, SECOND_CONFIRMATION_SCOPE)
        self._clear()
        return result

    @property
    def cleared(self) -> bool:
        return self._reader is None


__all__ = [
    "M63_FIRST_CONFIRMATION_TEXT",
    "M63_MANUAL_REMOVAL_TEXT",
    "M63_SECOND_CONFIRMATION_TEXT",
    "OneShotM63LiteralParser",
]
