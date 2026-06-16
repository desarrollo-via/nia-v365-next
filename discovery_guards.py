"""
discovery_guards.py — Protección de contexto en descubrimiento de producto.

Evita que enriquecimiento con libros técnicos o respuestas como "no se"
desvíen el flujo (p. ej. botas dieléctricas → termopar/RTD).
"""

from __future__ import annotations

import re
from typing import Optional

# Productos EPI / seguridad: no usar libros de instrumentación industrial.
KEYWORDS_EPI_SEGURIDAD = (
    "bota",
    "botas",
    "calzado",
    "dielectric",
    "dieléctric",
    "dieléctrica",
    "guante",
    "guantes",
    "casco",
    "cascos",
    "arnes",
    "arnés",
    "overol",
    "chaleco",
    "proteccion personal",
    "protección personal",
    "epi",
    "epp",
    "seguridad industrial",
    "aislante",
)

RESPUESTAS_DESCONOCIDAS = {
    "no se",
    "no sé",
    "no lo se",
    "no lo sé",
    "desconozco",
    "no tengo idea",
    "no sabria",
    "no sabría",
    "ni idea",
    "cualquiera",
    "da igual",
    "no importa",
}

RESPUESTAS_SIN_VALOR_BUSQUEDA = {
    "otro",
    "otra",
    "ninguno",
    "ninguna",
    "diferente",
}

# Términos de instrumentación que no deben mezclarse con EPI.
TERMINOS_INSTRUMENTACION = (
    "termopar",
    "rtd",
    "pt100",
    "doppler",
    "transmisor",
    "controlador",
    "pid",
    "4-20",
    "hart",
    "modbus",
    "plc",
    "valvula",
    "válvula",
    "caudalimetro",
    "caudalímetro",
    "psicrometro",
    "psicrómetro",
)

PREGUNTAS_EPI_BOTAS = [
    "¿Qué clase de voltaje o nivel de protección dieléctrica necesitas?",
    "¿Qué talla o rango de calzado requieres?",
    "¿Necesitas alguna norma o característica adicional (punta de acero, antideslizante, etc.)?",
]

PREGUNTAS_EPI_GENERAL = [
    "¿Para qué aplicación o nivel de protección lo necesitas?",
    "¿Qué talla, medida o rango de protección requieres?",
    "¿Necesitas alguna norma o certificación específica?",
]


def _opcion(valor_id: str, label: str, valor: str) -> dict:
    return {"id": valor_id, "label": label, "valor": valor}


def preguntas_epi_con_opciones(
    texto_ancla: str,
    respuestas: Optional[list] = None,
) -> list[dict]:
    """
    Preguntas EPI con botones, coherentes con el producto pedido.
    """
    t = (texto_ancla or "").lower()
    conocidas = respuestas_utiles(respuestas or [])

    if "bota" in t or "calzado" in t:
        return [
            {
                "texto": "¿Qué clase de voltaje o nivel de protección dieléctrica necesitas?",
                "opciones": [
                    _opcion("1", "Hasta 15 kV", "15 kV"),
                    _opcion("2", "Hasta 20 kV", "20 kV"),
                    _opcion("3", "Hasta 30 kV", "30 kV"),
                    _opcion("4", "Otro", "otro"),
                ],
            },
            {
                "texto": "¿Qué talla o rango de calzado requieres?",
                "opciones": [
                    _opcion("1", "Talla 38-40", "38-40"),
                    _opcion("2", "Talla 41-43", "41-43"),
                    _opcion("3", "Talla 44-46", "44-46"),
                    _opcion("4", "Otro", "otro"),
                ],
            },
            {
                "texto": "¿Necesitas alguna característica adicional?",
                "opciones": [
                    _opcion("1", "Punta de acero", "punta de acero"),
                    _opcion("2", "Antideslizante", "antideslizante"),
                    _opcion("3", "Sin requisito extra", "sin requisito extra"),
                    _opcion("4", "Otro", "otro"),
                ],
            },
        ]

    if "guante" in t:
        return [
            {
                "texto": "¿Qué clase de voltaje necesitas para los guantes?",
                "opciones": [
                    _opcion("1", "Hasta 1 kV", "1 kV"),
                    _opcion("2", "Hasta 17 kV", "17 kV"),
                    _opcion("3", "Hasta 36 kV", "36 kV"),
                    _opcion("4", "Otro", "otro"),
                ],
            },
            {
                "texto": "¿Qué talla necesitas?",
                "opciones": [
                    _opcion("1", "S", "S"),
                    _opcion("2", "M", "M"),
                    _opcion("3", "L", "L"),
                    _opcion("4", "XL", "XL"),
                ],
            },
            {
                "texto": "¿Algún requisito adicional?",
                "opciones": [
                    _opcion("1", "Palmado reforzado", "palmado reforzado"),
                    _opcion("2", "Sin requisito extra", "sin requisito extra"),
                    _opcion("3", "Otro", "otro"),
                ],
            },
        ]

    if conocidas:
        return [
            {
                "texto": "¿Puedes indicar marca, referencia o norma que necesitas?",
                "opciones": [
                    _opcion("1", "Tengo referencia", "tengo referencia"),
                    _opcion("2", "No tengo referencia", "no tengo referencia"),
                    _opcion("3", "Otro", "otro"),
                ],
            },
            {
                "texto": "¿Qué talla o medida requieres?",
                "opciones": [
                    _opcion("1", "Medida estándar", "medida estandar"),
                    _opcion("2", "Medida especial", "medida especial"),
                    _opcion("3", "Otro", "otro"),
                ],
            },
            {
                "texto": "¿Algún requisito adicional de protección?",
                "opciones": [
                    _opcion("1", "Norma específica", "norma especifica"),
                    _opcion("2", "Sin requisito extra", "sin requisito extra"),
                    _opcion("3", "Otro", "otro"),
                ],
            },
        ]

    return [
        {
            "texto": PREGUNTAS_EPI_GENERAL[0],
            "opciones": [
                _opcion("1", "Protección eléctrica", "proteccion electrica"),
                _opcion("2", "Protección mecánica", "proteccion mecanica"),
                _opcion("3", "Otro", "otro"),
            ],
        },
        {
            "texto": PREGUNTAS_EPI_GENERAL[1],
            "opciones": [
                _opcion("1", "Talla estándar", "talla estandar"),
                _opcion("2", "Talla especial", "talla especial"),
                _opcion("3", "Otro", "otro"),
            ],
        },
        {
            "texto": PREGUNTAS_EPI_GENERAL[2],
            "opciones": [
                _opcion("1", "Sí, norma específica", "norma especifica"),
                _opcion("2", "No", "no"),
                _opcion("3", "Otro", "otro"),
            ],
        },
    ]


def es_respuesta_desconocida(mensaje: str) -> bool:
    t = (mensaje or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" .,!¡¿?")
    return t in RESPUESTAS_DESCONOCIDAS


def es_producto_epi_seguridad(texto: str) -> bool:
    t = (texto or "").lower()
    return any(kw in t for kw in KEYWORDS_EPI_SEGURIDAD)


def texto_ancla_desde_ctx(necesidad_ctx: Optional[dict], texto_fallback: str = "") -> str:
    ctx = necesidad_ctx or {}
    for clave in ("texto_original", "query_evaluada"):
        valor = str(ctx.get(clave) or "").strip()
        if valor:
            return valor
    return str(texto_fallback or "").strip()


def es_respuesta_sin_valor_busqueda(mensaje: str) -> bool:
    t = (mensaje or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" .,!¡¿?")
    return t in RESPUESTAS_SIN_VALOR_BUSQUEDA


def respuestas_utiles(respuestas: list) -> list:
    resultado = []
    for respuesta in respuestas or []:
        txt = str(respuesta or "").strip()
        if (
            not txt
            or es_respuesta_desconocida(txt)
            or es_respuesta_sin_valor_busqueda(txt)
        ):
            continue
        resultado.append(txt)
    return resultado


def construir_texto_limpio_descubrimiento(
    necesidad_ctx: Optional[dict],
    mensaje_actual: str = "",
) -> str:
    """
    Arma texto para búsqueda/preguntas sin respuestas vacías ni ruido de libros.
    """
    ctx = necesidad_ctx or {}
    partes = []

    texto_original = str(ctx.get("texto_original") or "").strip()
    if texto_original:
        partes.append(texto_original)

    for respuesta in respuestas_utiles(ctx.get("respuestas_tecnicas") or []):
        partes.append(respuesta)

    mensaje = str(mensaje_actual or "").strip()
    if mensaje and not es_respuesta_desconocida(mensaje):
        partes.append(mensaje)

    return " ".join(partes).strip()


def filtrar_terminos_libros(terminos: list, texto_ancla: str) -> list:
    """
    Evita mezclar conceptos de instrumentación cuando el producto es EPI.
    """
    if not terminos:
        return []

    ancla = (texto_ancla or "").lower()
    if not es_producto_epi_seguridad(ancla):
        return list(terminos)

    filtrados = []
    for termino in terminos:
        t = str(termino or "").lower()
        if any(inst in t for inst in TERMINOS_INSTRUMENTACION):
            continue
        filtrados.append(termino)

    return filtrados


def preguntas_refino_epi(texto_ancla: str, respuestas: Optional[list] = None) -> list:
    """
    Preguntas coherentes cuando el catálogo no devolvió match para EPI.
    Devuelve dicts con opciones para mostrar botones en el frontend.
    """
    return preguntas_epi_con_opciones(texto_ancla, respuestas)


def queries_alternativas_epi(texto_ancla: str, respuestas: Optional[list] = None) -> list:
    """
    Variantes de búsqueda para EPI cuando la consulta acumulada no devuelve nada.
    """
    t = (texto_ancla or "").lower()
    queries = []

    if "bota" in t or "calzado" in t:
        queries.extend(
            [
                "botas dielectricas",
                "botas dieléctricas",
                "calzado dielectrico electricidad",
                "botas seguridad electrica",
            ]
        )

        for respuesta in respuestas_utiles(respuestas or []):
            r = respuesta.lower()
            if "v" in r or "volt" in r:
                queries.append(f"botas dielectricas {respuesta}")

    if "guante" in t:
        queries.extend(["guantes dielectricos", "guantes electricidad"])

    vistos = set()
    unicos = []
    for q in queries:
        qn = q.strip().lower()
        if qn and qn not in vistos:
            vistos.add(qn)
            unicos.append(q.strip())
    return unicos
