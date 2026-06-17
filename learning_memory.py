"""
learning_memory.py — Memoria de aprendizaje sí/no para NIA v365.

Guarda confirmaciones y rechazos del cliente (producto, cotización, proforma)
con contexto de búsqueda e historial conversacional reciente.

Uso:
- Registrar feedback cuando el cliente responde sí o no.
- Excluir productos rechazados en búsquedas futuras del mismo cliente.
- Consultar preferencias aceptadas para priorizar opciones similares.
"""

from __future__ import annotations

import contextvars
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from memory import get_clientes_collection, get_db

logger = logging.getLogger(__name__)

APRENDIZAJE_COLLECTION = os.getenv("MONGO_LEARNING_COLLECTION", "nia_nueva_aprendizaje")
MAX_EVENTOS_POR_CLAVE = 500
MAX_HISTORIAL_SLICE = 30
MAX_CODIGOS_RESUMEN = 100

aprendizaje_activo: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "nia_aprendizaje",
    default=None,
)


def get_aprendizaje_collection():
    db = get_db()
    return db[APRENDIZAJE_COLLECTION]


def resolver_clave_aprendizaje(
    phone_id: Optional[str] = None,
    cliente: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """
    Identificador estable para memoria entre sesiones.

    Prioridad: phone_id → email del cliente → session_id (solo web anónimo).
    """
    if phone_id and str(phone_id).strip():
        return f"phone:{str(phone_id).strip()}"

    cliente = cliente or {}
    email = cliente.get("email")
    if email and str(email).strip():
        return f"email:{str(email).strip().lower()}"

    if session_id and str(session_id).strip():
        return f"session:{str(session_id).strip()}"

    return None


def extraer_slice_historial(historial: Optional[list]) -> list:
    """
    Conserva los últimos turnos relevantes para auditoría y aprendizaje.
    """
    if not historial:
        return []

    slice_hist = historial[-MAX_HISTORIAL_SLICE:]
    resultado = []

    for turno in slice_hist:
        if not isinstance(turno, dict):
            continue

        role = turno.get("role")
        content = turno.get("content")

        if role not in {"user", "assistant"} or not content:
            continue

        entrada = {
            "role": role,
            "content": str(content).strip()[:2000],
        }

        ts = turno.get("ts")
        if ts:
            entrada["ts"] = ts

        resultado.append(entrada)

    return resultado


def construir_contexto_aprendizaje_desde_necesidad(necesidad_ctx: Optional[dict]) -> dict:
    """
    Extrae contexto técnico útil desde necesidad_ctx o contexto_aprendizaje guardado.
    """
    necesidad_ctx = necesidad_ctx or {}

    if necesidad_ctx.get("contexto_aprendizaje"):
        base = dict(necesidad_ctx["contexto_aprendizaje"])
    else:
        base = {
            "texto_original": necesidad_ctx.get("texto_original"),
            "query_evaluada": necesidad_ctx.get("query_evaluada"),
            "dominio": necesidad_ctx.get("dominio"),
            "palabra_clave": necesidad_ctx.get("palabra_clave"),
            "nivel_1": (
                necesidad_ctx.get("nivel_1_seleccionado")
                or necesidad_ctx.get("tipo_corta_seleccionado")
            ),
            "respuestas_hibridas": list(
                necesidad_ctx.get("respuestas_hibridas_previas") or []
            ),
            "respuestas_tecnicas": list(necesidad_ctx.get("respuestas_tecnicas") or []),
            "flujo": necesidad_ctx.get("flujo_descubrimiento"),
        }

    limpio = {}
    for clave, valor in base.items():
        if valor is None:
            continue
        if valor == "":
            continue
        if valor == []:
            continue
        if valor == {}:
            continue
        limpio[clave] = valor

    return limpio


def construir_evento_feedback(
    *,
    clave_aprendizaje: str,
    tipo: str,
    categoria: str,
    mensaje_usuario: str,
    session_id: Optional[str] = None,
    producto: Optional[dict] = None,
    contexto: Optional[dict] = None,
    historial: Optional[list] = None,
) -> dict:
    """
    Arma el documento de feedback listo para persistir en MongoDB.
    """
    if tipo not in {"si", "no"}:
        raise ValueError(f"tipo de feedback inválido: {tipo}")

    producto_limpio = None
    if producto:
        producto_limpio = {
            "codigo": producto.get("codigo"),
            "nombre": producto.get("nombre") or producto.get("descripcion_corta"),
            "nivel_1": producto.get("nivel_1") or producto.get("tipo_corta"),
            "marca": producto.get("marca"),
        }
        producto_limpio = {
            k: v for k, v in producto_limpio.items() if v not in {None, ""}
        }

    return {
        "clave_aprendizaje": clave_aprendizaje,
        "session_id": session_id,
        "tipo": tipo,
        "categoria": categoria,
        "mensaje_usuario": (mensaje_usuario or "").strip()[:500],
        "producto": producto_limpio,
        "contexto": contexto or {},
        "historial_slice": extraer_slice_historial(historial),
        "created_at": datetime.now(timezone.utc),
    }


def _vacio_memoria() -> dict:
    return {
        "productos_rechazados": [],
        "productos_aceptados": [],
        "nivel_1_rechazados": [],
        "nivel_1_aceptados": [],
        "dominios_aceptados": [],
        "dominios_rechazados": [],
        "cotizaciones_aceptadas": 0,
        "cotizaciones_rechazadas": 0,
    }


def _acumular_resumen(memoria: dict, evento: dict) -> dict:
    """
    Actualiza resumen en memoria a partir de un evento nuevo.
    """
    memoria = dict(memoria or _vacio_memoria())
    tipo = evento.get("tipo")
    categoria = evento.get("categoria")
    producto = evento.get("producto") or {}
    contexto = evento.get("contexto") or {}

    codigo = producto.get("codigo")
    nivel_1 = producto.get("nivel_1") or contexto.get("nivel_1")
    dominio = contexto.get("dominio")

    if categoria in {"producto", "relacionado"} and codigo:
        lista = (
            "productos_aceptados" if tipo == "si" else "productos_rechazados"
        )
        codigos = list(memoria.get(lista) or [])
        if codigo not in codigos:
            codigos.append(codigo)
        memoria[lista] = codigos[-MAX_CODIGOS_RESUMEN:]

    if categoria in {"producto", "relacionado"} and nivel_1:
        lista_n1 = (
            "nivel_1_aceptados" if tipo == "si" else "nivel_1_rechazados"
        )
        niveles = list(memoria.get(lista_n1) or [])
        if nivel_1 not in niveles:
            niveles.append(nivel_1)
        memoria[lista_n1] = niveles[-MAX_CODIGOS_RESUMEN:]

    if dominio:
        lista_dom = (
            "dominios_aceptados" if tipo == "si" else "dominios_rechazados"
        )
        dominios = list(memoria.get(lista_dom) or [])
        if dominio not in dominios:
            dominios.append(dominio)
        memoria[lista_dom] = dominios[-MAX_CODIGOS_RESUMEN:]

    if categoria == "cotizacion":
        campo = (
            "cotizaciones_aceptadas"
            if tipo == "si"
            else "cotizaciones_rechazadas"
        )
        memoria[campo] = int(memoria.get(campo) or 0) + 1

    return memoria


async def ensure_index_aprendizaje():
    """
    Índices para consultas por cliente y limpieza por fecha.
    """
    collection = get_aprendizaje_collection()

    await collection.create_index(
        [("clave_aprendizaje", 1), ("created_at", -1)],
        background=True,
        name="idx_clave_created_at",
    )

    await collection.create_index(
        [("clave_aprendizaje", 1), ("tipo", 1), ("categoria", 1)],
        background=True,
        name="idx_clave_tipo_categoria",
    )

    await collection.create_index(
        [("producto.codigo", 1)],
        background=True,
        name="idx_producto_codigo",
        partialFilterExpression={"producto.codigo": {"$type": "string"}},
    )


async def registrar_feedback(evento: dict) -> Optional[dict]:
    """
    Persiste un evento de feedback y devuelve memoria agregada actualizada.
    """
    clave = evento.get("clave_aprendizaje")
    if not clave:
        return None

    collection = get_aprendizaje_collection()

    try:
        await collection.insert_one(evento)

        total = await collection.count_documents({"clave_aprendizaje": clave})
        if total > MAX_EVENTOS_POR_CLAVE:
            sobrantes = total - MAX_EVENTOS_POR_CLAVE
            viejos = (
                await collection.find({"clave_aprendizaje": clave}, {"_id": 1})
                .sort("created_at", 1)
                .limit(sobrantes)
                .to_list(length=sobrantes)
            )
            ids = [doc["_id"] for doc in viejos]
            if ids:
                await collection.delete_many({"_id": {"$in": ids}})

        memoria = await obtener_memoria_aprendizaje(clave, recalcular=True)
        await _actualizar_resumen_en_cliente(clave, memoria)

        logger.info(
            "Aprendizaje registrado clave=%s tipo=%s categoria=%s codigo=%s",
            clave,
            evento.get("tipo"),
            evento.get("categoria"),
            (evento.get("producto") or {}).get("codigo"),
        )

        return memoria

    except Exception as exc:
        logger.warning(
            "No fue posible registrar aprendizaje clave=%s error=%s",
            clave,
            exc,
        )
        return None


async def _actualizar_resumen_en_cliente(clave: str, memoria: dict):
    """
    Si la clave es phone:*, guarda resumen en el cliente permanente.
    """
    if not clave.startswith("phone:"):
        return

    phone_id = clave.split(":", 1)[1]
    if not phone_id:
        return

    collection = get_clientes_collection()

    try:
        await collection.update_one(
            {"phone_id": phone_id},
            {
                "$set": {
                    "aprendizaje_resumen": memoria,
                    "aprendizaje_updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=False,
        )
    except Exception as exc:
        logger.warning(
            "No fue posible actualizar resumen aprendizaje phone_id=%s error=%s",
            phone_id,
            exc,
        )


async def obtener_memoria_aprendizaje(
    clave: Optional[str],
    recalcular: bool = False,
) -> dict:
    """
    Devuelve resumen agregado de sí/no para una clave de cliente.
    """
    if not clave:
        return _vacio_memoria()

    if not recalcular and clave.startswith("phone:"):
        phone_id = clave.split(":", 1)[1]
        cliente = await get_clientes_collection().find_one(
            {"phone_id": phone_id},
            {"_id": 0, "aprendizaje_resumen": 1},
        )
        if cliente and cliente.get("aprendizaje_resumen"):
            return cliente["aprendizaje_resumen"]

    collection = get_aprendizaje_collection()

    try:
        eventos = (
            await collection.find(
                {"clave_aprendizaje": clave},
                {"_id": 0, "tipo": 1, "categoria": 1, "producto": 1, "contexto": 1},
            )
            .sort("created_at", -1)
            .limit(MAX_EVENTOS_POR_CLAVE)
            .to_list(length=MAX_EVENTOS_POR_CLAVE)
        )
    except Exception as exc:
        logger.warning(
            "No fue posible leer aprendizaje clave=%s error=%s",
            clave,
            exc,
        )
        return _vacio_memoria()

    memoria = _vacio_memoria()
    for evento in reversed(eventos):
        memoria = _acumular_resumen(memoria, evento)

    return memoria


def codigos_a_excluir(memoria: Optional[dict] = None) -> set:
    """
    Códigos de producto que el cliente rechazó explícitamente.
    """
    memoria = memoria or aprendizaje_activo.get() or {}
    return set(memoria.get("productos_rechazados") or [])


def filtrar_productos_por_aprendizaje(
    productos: list,
    memoria: Optional[dict] = None,
) -> list:
    """
    Elimina candidatos previamente rechazados por el cliente.
    """
    if not productos:
        return productos

    excluir = codigos_a_excluir(memoria)
    if not excluir:
        return productos

    filtrados = [p for p in productos if p.get("codigo") not in excluir]

    if filtrados:
        return filtrados

    logger.info(
        "Todos los candidatos estaban rechazados (%s); se conserva lista original.",
        len(excluir),
    )
    return productos


def activar_memoria_aprendizaje(memoria: Optional[dict]):
    """
    Fija memoria de aprendizaje para el turno actual (context var).
    """
    aprendizaje_activo.set(memoria or _vacio_memoria())


def desactivar_memoria_aprendizaje():
    """
    Limpia context var al terminar el turno.
    """
    aprendizaje_activo.set(None)
