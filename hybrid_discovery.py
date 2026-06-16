"""
hybrid_discovery.py — Modo 3 híbrida guiada por libros + catálogo.

Flujo:
1. Cliente expresa necesidad técnica (ej. "quiero medir temperatura").
2. Se arma pool inicial de candidatos en MongoDB (dominio + libros).
3. Hasta 5 preguntas con 3 opciones + Otro, filtrando candidatos cada turno.
4. Al quedar un candidato claro → código/producto final.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

from catalog import buscar_por_texto, evaluar_coincidencia, normalizar_producto
from knowledge import contexto_para_agente, detectar_dominio
from memory import get_db
from product_discovery import (
    PRODUCTS_COLLECTION,
    analizar_campos_discriminantes,
    _articulo_campo,
    _etiqueta_campo,
    _formatear_nivel_1,
    _normalizar_texto,
)

logger = logging.getLogger("nia.hybrid_discovery")

MAX_PREGUNTAS_HIBRIDAS = 5
MAX_OPCIONES = 3
MAX_CANDIDATOS_POOL = 200

PALABRAS_NECESIDAD = (
    "medir",
    "medicion",
    "medición",
    "controlar",
    "monitorear",
    "monitorizar",
    "registrar",
    "sensor",
    "transmisor",
    "indicador",
)

DOMINIO_TERMINOS_BUSQUEDA = {
    "temperatura": ["termometro", "temperatura", "rtd", "termopar", "pt100"],
    "presion": ["presion", "presión", "transmisor", "manometro", "manómetro"],
    "nivel": ["nivel", "level", "radar", "ultrasonido", "flotador"],
    "caudal": ["caudal", "flujo", "flowmeter", "medidor"],
    "humedad": [
        "humedad", "rocio", "rocío", "termohigrometro", "termohigrómetro",
        "higrometro", "higrómetro", "psicrometro", "psicrómetro", "dew point",
    ],
    "transmisores": ["transmisor", "transmitter", "4-20ma"],
    "valvulas_control": ["valvula", "válvula", "actuador"],
    "analitica_proceso": ["ph", "conductividad", "analizador", "analyzer"],
}

# Frases compuestas → dominio (prioridad sobre fuzzy; evita medir≈medidor→caudal).
FRASES_DOMINIO_PRIORITARIAS: tuple[tuple[str, str], ...] = (
    ("punto de rocio", "humedad"),
    ("punto de rocío", "humedad"),
    ("punto rocio", "humedad"),
    ("dew point", "humedad"),
    ("humedad relativa", "humedad"),
    ("humedad absoluta", "humedad"),
    ("termohigrometro", "humedad"),
    ("termohigrómetro", "humedad"),
    ("psicrometro", "humedad"),
    ("psicrómetro", "humedad"),
    ("higrometro", "humedad"),
    ("higrómetro", "humedad"),
    ("medir nivel", "nivel"),
    ("medicion de nivel", "nivel"),
    ("medición de nivel", "nivel"),
    ("medir presion", "presion"),
    ("medir presión", "presion"),
    ("medir temperatura", "temperatura"),
    ("medir caudal", "caudal"),
    ("medir flujo", "caudal"),
)

TOKENS_IGNORAR_FUZZY_DOMINIO = frozenset({
    "medir", "medicion", "medición", "necesito", "neceito", "quiero", "busco",
    "controlar", "monitorear", "monitorizar", "registrar", "proceso", "punto",
    "necesita", "requiero", "debo",
})

APLICACIONES_POR_DOMINIO: dict[str, list[tuple[str, str]]] = {
    "temperatura": [
        ("alimentos", "Alimentos y cocina"),
        ("industrial", "Proceso industrial"),
        ("laboratorio", "Laboratorio o clínica"),
    ],
    "presion": [
        ("vapor", "Vapor o caldera"),
        ("liquidos", "Líquidos y tanques"),
        ("gases", "Gases o aire"),
    ],
    "nivel": [
        ("tanques", "Tanques de almacenamiento"),
        ("agua", "Agua o efluentes"),
        ("solidos", "Sólidos o silos"),
    ],
    "caudal": [
        ("agua", "Agua o líquidos"),
        ("aire", "Aire o gases"),
        ("industrial", "Proceso industrial"),
    ],
    "humedad": [
        ("aire", "Aire comprimido o gases"),
        ("proceso", "Proceso industrial"),
        ("laboratorio", "Laboratorio o calidad"),
    ],
    "transmisores": [
        ("presion", "Presión"),
        ("temperatura", "Temperatura"),
        ("nivel", "Nivel o caudal"),
    ],
}

# Segunda pregunta según dónde se mide (fluido/material del proceso).
FLUIDOS_POR_APLICACION: dict[str, dict[str, list[tuple[str, str]]]] = {
    "nivel": {
        "tanques": [
            ("agua", "Agua"),
            ("aceite", "Aceite o combustible"),
            ("quimico", "Químico o corrosivo"),
            ("granel", "Sólido o polvo"),
        ],
        "solidos": [
            ("grano", "Grano o cereal"),
            ("polvo", "Polvo o material fino"),
            ("granel", "Material a granel"),
        ],
    },
    "presion": {
        "liquidos": [
            ("agua", "Agua"),
            ("aceite", "Aceite o lubricante"),
            ("quimico", "Químico o corrosivo"),
        ],
        "vapor": [
            ("vapor", "Vapor saturado"),
            ("agua", "Agua caliente"),
            ("gas", "Gas o aire"),
        ],
    },
    "temperatura": {
        "alimentos": [
            ("liquido", "Líquido o salsa"),
            ("solido", "Sólido o grano"),
            ("ambiente", "Ambiente o cámara"),
        ],
        "industrial": [
            ("liquido", "Líquido de proceso"),
            ("gas", "Gas o vapor"),
            ("superficie", "Superficie o sólido"),
        ],
    },
    "caudal": {
        "agua": [
            ("potable", "Agua potable"),
            ("residual", "Agua residual"),
            ("industrial", "Agua de proceso"),
        ],
        "aire": [
            ("comprimido", "Aire comprimido"),
            ("natural", "Gas natural"),
            ("proceso", "Gas de proceso"),
        ],
    },
    "humedad": {
        "aire": [
            ("comprimido", "Aire comprimido"),
            ("gas", "Gas industrial o inerte"),
            ("ambiente", "Ambiente o sala técnica"),
        ],
        "proceso": [
            ("vapor", "Vapor o gas húmedo"),
            ("gases", "Gases de proceso"),
            ("ambiente", "Ambiente industrial"),
        ],
        "laboratorio": [
            ("ambiente", "Ambiente controlado"),
            ("calibracion", "Calibración o patrones"),
            ("muestras", "Muestras o cámaras"),
        ],
    },
}

PREGUNTA_APLICACION_POR_DOMINIO = {
    "nivel": "¿Dónde vas a medir el nivel?",
    "temperatura": "¿Dónde vas a medir la temperatura?",
    "presion": "¿En qué punto del proceso necesitas medir la presión?",
    "caudal": "¿Dónde necesitas medir el caudal?",
    "humedad": "¿Dónde necesitas medir la humedad o el punto de rocío?",
}

NIVEL_1_INCLUIR_POR_DOMINIO: dict[str, tuple[str, ...]] = {
    "temperatura": (
        "termometro", "temperatura", "termopar", "rtd", "pt100",
        "infrarroj", "bimetalic", "control", "transmisor",
    ),
    "nivel": (
        "nivel", "level", "radar", "ultrason", "flotador", "interruptor",
    ),
    "presion": (
        "presion", "presión", "manometro", "manómetro", "transmisor",
    ),
    "caudal": (
        "caudal", "flujo", "flow", "rotametro", "medidor",
    ),
    "humedad": (
        "humedad", "higro", "termohigro", "psicrom", "higrom", "deshumid",
    ),
}

NIVEL_1_EXCLUIR_POR_DOMINIO: dict[str, tuple[str, ...]] = {
    "temperatura": (
        "manometro", "manómetro", "presion", "presión", "valvula", "válvula",
        "nivel", "caudal", "flujo", "bomba", "rodamiento", "celda-de-carga",
    ),
    "nivel": (
        "manometro", "termometro", "temperatura", "bomba", "rodamiento",
        "guia", "linea-cruzada", "linea cruzada", "velocidad", "pistola",
        "construcc", "bosch", "niveles-laser",
    ),
    "presion": (
        "termometro", "temperatura", "nivel", "caudal", "bomba",
    ),
    "humedad": (
        "caudal", "flujo", "nivel", "presion", "presión", "manometro",
        "termometro", "arnes", "bomba", "turbina",
    ),
}

BOOST_NIVEL_1_CONTEXTO: dict[tuple[str, str, str], tuple[str, ...]] = {
    ("temperatura", "alimentos", "solido"): (
        "termometro", "infrarroj", "termopar", "pt100", "cocina", "alimento",
    ),
    ("temperatura", "alimentos", "liquido"): (
        "termometro", "bulbo", "bimetalic", "rtd", "cocina", "alimento",
    ),
    ("temperatura", "alimentos", "ambiente"): (
        "infrarroj", "termometro", "control", "cocina",
    ),
    ("temperatura", "industrial", "liquido"): (
        "transmisor", "termopar", "rtd", "termometro",
    ),
    ("nivel", "tanques", "agua"): (
        "interruptor", "transmisor", "radar", "ultrason", "flotador",
    ),
    ("nivel", "tanques", "aceite"): (
        "interruptor", "transmisor", "flotador",
    ),
    ("nivel", "tanques", "granel"): (
        "radar", "tdr", "guiado", "rotatorio", "transmisor",
    ),
    ("nivel", "tanques", "polvo"): (
        "radar", "tdr", "guiado", "rotatorio",
    ),
    ("nivel", "solidos", "grano"): (
        "radar", "tdr", "rotatorio",
    ),
}

# Sólidos/polvo: ultrasonido no es adecuado (polvo, cemento, grano). Radar es la opción típica.
MATERIALES_SOLIDO_POLVO = frozenset({"granel", "polvo", "grano", "solido"})

PALABRAS_MATERIAL_SOLIDO = frozenset({
    "cemento", "concreto", "polvo", "grano", "arena", "cal", "harina",
    "solido", "granel", "cereal", "yeso", "silice", "carbon", "mineral",
})

TECNOLOGIA_PREFERIDA_SOLIDO = ("radar", "tdr", "guiado", "rotatorio", "capacit")
TECNOLOGIA_EXCLUIR_SOLIDO = ("ultrason", "ultrasonic")

# Slugs NIVEL_1 con productos aptos para sólidos/polvo (radar TDR, capacitancia, paleta…).
_REGEX_TECNO_PRODUCTO_SOLIDO = (
    r"radar|tdr|guiad|onda guiada|capacit|rotatoria|vibracion|radiofrecuencia"
)
_REGEX_EXCLUIR_PRODUCTO_SOLIDO = (
    r"ultrason|velocidad|guia laser|linea cruzada|inclinometro|topografia|"
    r"retractil|para pozos|tubos de vidrio|medidores de inclinacion"
)
_SLUGS_NIVEL_SOLIDO_PRIORIDAD = ("transmisor-de-nivel", "interruptores-de-nivel")


def _detectar_dominio_por_frases(texto: str) -> Optional[str]:
    """Frases compuestas con prioridad (ej. punto de rocío → humedad, no caudal)."""
    t = _normalizar_texto(texto)
    if not t:
        return None
    for frase, dominio in FRASES_DOMINIO_PRIORITARIAS:
        if _normalizar_texto(frase) in t:
            return dominio
    return None


def _inferir_dominio_tolerante(texto: str) -> Optional[str]:
    """
    Detecta dominio técnico aunque haya typos leves (ej. temperataura).
    """
    from difflib import SequenceMatcher

    dominio_frases = _detectar_dominio_por_frases(texto)
    if dominio_frases:
        return dominio_frases

    dominio = detectar_dominio(texto)
    if dominio:
        return dominio

    t = _normalizar_texto(texto)
    for dom, terminos in DOMINIO_TERMINOS_BUSQUEDA.items():
        if any(_normalizar_texto(term) in t for term in terminos):
            return dom

    tokens = [
        tok
        for tok in re.split(r"\s+", t)
        if len(tok) >= 4 and tok not in TOKENS_IGNORAR_FUZZY_DOMINIO
    ]
    mejor_dom = None
    mejor_score = 0.0

    for dom, terminos in DOMINIO_TERMINOS_BUSQUEDA.items():
        refs = [_normalizar_texto(term) for term in terminos]
        for token in tokens:
            for ref in refs:
                score = SequenceMatcher(None, token, ref).ratio()
                if score > mejor_score:
                    mejor_score = score
                    mejor_dom = dom

    if mejor_dom and mejor_score >= 0.82:
        return mejor_dom

    return None


def es_necesidad_hibrida_guiada(texto: str) -> bool:
    """
    Necesidad técnica sin specs suficientes para búsqueda directa.
    Ej: "quiero medir temperatura", "necesito controlar presion en caldera".
    """
    if not (texto or "").strip():
        return False

    t = _normalizar_texto(texto)
    dominio = _inferir_dominio_tolerante(texto)

    if not dominio:
        return False

    tiene_intencion = any(p in t for p in PALABRAS_NECESIDAD)
    if not tiene_intencion:
        return False

    tiene_variable = any(
        _normalizar_texto(kw) in t
        for kw in DOMINIO_TERMINOS_BUSQUEDA.get(dominio, [])[:5]
    )

    return tiene_variable or dominio in (
        "temperatura", "presion", "nivel", "caudal", "humedad",
    )


def _construir_opciones_hibridas(valores: list[str]) -> list[dict]:
    opciones = []
    for idx, valor in enumerate(valores[:MAX_OPCIONES], start=1):
        valor_txt = str(valor).strip()
        if not valor_txt:
            continue
        opciones.append({"id": str(idx), "label": valor_txt, "valor": valor_txt})

    opciones.append(
        {
            "id": str(len(opciones) + 1),
            "label": "Otro",
            "valor": "otro",
        }
    )
    return opciones


def _variable_dominio(dominio: str) -> str:
    return {
        "temperatura": "temperatura",
        "presion": "presión",
        "nivel": "nivel",
        "caudal": "caudal",
        "humedad": "humedad",
        "transmisores": "variable de proceso",
        "valvulas_control": "válvula de control",
        "analitica_proceso": "parámetro analítico",
    }.get(dominio, "medición")


def _frase_variable(dominio: str) -> str:
    return {
        "temperatura": "la temperatura",
        "presion": "la presión",
        "nivel": "el nivel",
        "caudal": "el caudal",
        "humedad": "la humedad o el punto de rocío",
        "transmisores": "la variable de proceso",
        "valvulas_control": "la válvula de control",
        "analitica_proceso": "el parámetro analítico",
    }.get(dominio, "la medición")


def generar_pregunta_aplicacion(dominio: str) -> dict:
    """Primera pregunta: dónde se aplica la medición."""
    opciones_raw = APLICACIONES_POR_DOMINIO.get(dominio) or [
        ("industrial", "Proceso industrial"),
        ("laboratorio", "Laboratorio"),
        ("mantenimiento", "Mantenimiento o servicio"),
    ]
    texto = PREGUNTA_APLICACION_POR_DOMINIO.get(
        dominio,
        f"¿Dónde vas a medir o controlar {_frase_variable(dominio)}?",
    )

    return {
        "tipo": "aplicacion",
        "campo": "aplicacion",
        "texto": texto,
        "opciones": _construir_opciones_hibridas([etiqueta for _, etiqueta in opciones_raw]),
        "mapa_valores": {etiqueta: clave for clave, etiqueta in opciones_raw},
    }


def _clave_aplicacion(respuestas_previas: list[dict]) -> str:
    for item in reversed(respuestas_previas):
        if item.get("campo") == "aplicacion":
            return str(item.get("clave") or item.get("valor") or "").strip()
    return ""


def _inferir_clave_material(texto: str) -> str:
    """Mapea texto libre (cemento, polvo…) a clave de fluido para boost contextual."""
    t = _normalizar_texto(texto)
    mapa = {
        "cemento": "granel",
        "concreto": "granel",
        "polvo": "polvo",
        "grano": "grano",
        "cereal": "grano",
        "arena": "granel",
        "cal": "granel",
        "harina": "polvo",
        "solido": "granel",
        "solidos": "granel",
        "granel": "granel",
    }
    for keyword, clave in mapa.items():
        if keyword in t:
            return clave
    return t


def _contexto_material_nivel(
    respuestas_previas: list[dict],
    texto_extra: str = "",
) -> dict:
    fluido_clave = _normalizar_texto(_clave_respuesta_campo(respuestas_previas, "fluido"))
    fluido_valor = ""
    for item in reversed(respuestas_previas or []):
        if item.get("campo") == "fluido":
            fluido_valor = str(item.get("valor") or "")
            break

    texto = _normalizar_texto(f"{fluido_valor} {texto_extra}")
    es_solido = (
        fluido_clave in MATERIALES_SOLIDO_POLVO
        or any(p in texto for p in PALABRAS_MATERIAL_SOLIDO)
    )
    es_liquido = fluido_clave in {"agua", "aceite", "quimico", "liquido"}

    return {
        "es_solido_polvo": es_solido,
        "es_liquido": es_liquido,
        "fluido_clave": fluido_clave,
        "fluido_valor": fluido_valor,
    }


def _tecnologias_nivel_para_material(
    ctx_material: dict,
    extractos_libros: Optional[list[str]] = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Reglas técnicas + refuerzo desde libros Creus/Kuphaldt.
    Sólidos/polvo/cemento → preferir radar, excluir ultrasonido.
    """
    if not ctx_material.get("es_solido_polvo"):
        if ctx_material.get("es_liquido"):
            return ("radar", "ultrason", "transmisor", "flotador"), ()
        return (), ()

    prefer = TECNOLOGIA_PREFERIDA_SOLIDO
    excluir = TECNOLOGIA_EXCLUIR_SOLIDO

    blob = _normalizar_texto(" ".join(extractos_libros or []))
    if blob:
        if any(w in blob for w in ("polvo", "solido", "grano", "cemento", "polvoriento")):
            if "radar" in blob or "tdr" in blob or "guiado" in blob:
                prefer = ("radar",) + prefer
        if any(w in blob for w in ("ultrason", "ultrasonic")) and any(
            w in blob for w in ("polvo", "solido", "polvoriento", "no ", "limitad", "no es")
        ):
            excluir = excluir + ("ultrason",)

    return prefer, excluir


def _bloque_tecnologia_item(texto: str) -> str:
    return _normalizar_texto(texto)


def _item_coincide_tecnologia(bloque: str, terminos: tuple[str, ...]) -> bool:
    return any(term in bloque for term in terminos)


def _filtrar_niveles_por_tecnologia(
    niveles: list[tuple[str, int]],
    prefer: tuple[str, ...],
    excluir: tuple[str, ...],
) -> list[tuple[str, int]]:
    if not niveles:
        return niveles

    filtrados = []
    for nivel, count in niveles:
        bloque = _bloque_tecnologia_item(f"{nivel} {_formatear_nivel_1(nivel)}")
        if excluir and _item_coincide_tecnologia(bloque, excluir):
            continue
        filtrados.append((nivel, count))

    if prefer and filtrados:
        scored = []
        for nivel, count in filtrados:
            bloque = _bloque_tecnologia_item(f"{nivel} {_formatear_nivel_1(nivel)}")
            score = sum(1 for term in prefer if term in bloque)
            scored.append((score, count, nivel))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        preferidos = [item for item in scored if item[0] > 0]
        if preferidos:
            return [(nivel, count) for _, count, nivel in preferidos[:6]]

    return filtrados or niveles


def filtrar_productos_por_tecnologia_material(
    productos: list[dict],
    respuestas_previas: list[dict],
    extractos_libros: Optional[list[str]] = None,
    texto_extra: str = "",
) -> list[dict]:
    ctx = _contexto_material_nivel(respuestas_previas, texto_extra=texto_extra)
    prefer, excluir = _tecnologias_nivel_para_material(ctx, extractos_libros)

    if not ctx.get("es_solido_polvo"):
        return productos

    filtrados = []
    for producto in productos:
        bloque = _bloque_producto(producto)
        nivel = _bloque_tecnologia_item(
            str(producto.get("nivel_1") or producto.get("categoria") or "")
        )
        bloque_full = f"{bloque} {nivel}"
        if excluir and _item_coincide_tecnologia(bloque_full, excluir):
            continue
        filtrados.append(producto)

    if not filtrados:
        return productos

    if prefer:
        scored = []
        for producto in filtrados:
            bloque = _bloque_producto(producto)
            nivel = str(producto.get("nivel_1") or producto.get("categoria") or "")
            bloque_full = _bloque_tecnologia_item(f"{bloque} {nivel}")
            score = sum(1 for term in prefer if term in bloque_full)
            scored.append((score, producto))
        scored.sort(key=lambda item: -item[0])
        radar_primero = [p for score, p in scored if score > 0]
        if radar_primero:
            resto = [p for score, p in scored if score == 0]
            return radar_primero + resto

    logger.info(
        "Filtro tecnología sólido/polvo: %s → %s productos (excluye ultrasonido)",
        len(productos),
        len(filtrados),
    )
    return filtrados


def filtrar_tipos_nivel_1_por_tecnologia(
    tipos: list[dict],
    respuestas_previas: list[dict],
    extractos_libros: Optional[list[str]] = None,
    texto_extra: str = "",
) -> list[dict]:
    ctx = _contexto_material_nivel(respuestas_previas, texto_extra=texto_extra)
    prefer, excluir = _tecnologias_nivel_para_material(ctx, extractos_libros)
    if not ctx.get("es_solido_polvo"):
        return tipos

    niveles = [(str(t.get("nivel_1") or ""), int(t.get("count") or 0)) for t in tipos]
    filtrados = _filtrar_niveles_por_tecnologia(niveles, prefer, excluir)
    mapa = {str(t.get("nivel_1") or ""): t for t in tipos if t.get("nivel_1")}
    resultado = [mapa[nivel] for nivel, _ in filtrados if nivel in mapa]
    return resultado or tipos


def _producto_es_ultrasonico(producto: dict) -> bool:
    bloque = _bloque_tecnologia_item(_bloque_producto(producto))
    nivel = _bloque_tecnologia_item(str(producto.get("nivel_1") or producto.get("categoria") or ""))
    return "ultrason" in f"{bloque} {nivel}"


def resolver_previas_hibridas(necesidad_ctx: dict) -> list[dict]:
    """
    Unifica contexto híbrido (cemento, tanque…) aunque la sesión perdió
    respuestas_hibridas_previas al pasar a corta_larga.
    """
    previas = list(necesidad_ctx.get("respuestas_hibridas_previas") or [])
    if previas:
        return previas

    hibridas = list(necesidad_ctx.get("respuestas_hibridas") or [])
    if hibridas:
        return hibridas

    partes = [
        str(necesidad_ctx.get("texto_original") or ""),
        str(necesidad_ctx.get("query_evaluada") or ""),
    ]
    partes.extend(
        str(r).strip()
        for r in (necesidad_ctx.get("respuestas_tecnicas") or [])
        if str(r).strip()
    )
    blob = _normalizar_texto(" ".join(p for p in partes if p))
    if not blob:
        return []

    inferidas: list[dict] = []
    if any(w in blob for w in PALABRAS_MATERIAL_SOLIDO):
        material = next((w for w in sorted(PALABRAS_MATERIAL_SOLIDO, key=len, reverse=True) if w in blob), "granel")
        inferidas.append(
            {
                "campo": "fluido",
                "clave": _inferir_clave_material(material),
                "valor": material,
            }
        )
    if any(w in blob for w in ("tanque", "almacenamiento", "silo")):
        inferidas.append(
            {
                "campo": "aplicacion",
                "clave": "tanques",
                "valor": "Tanques de almacenamiento",
            }
        )
    return inferidas


async def _tipos_nivel_1_desde_productos_solidos() -> list[dict]:
    """
    Agrupa NIVEL_1 con productos aptos para sólidos/polvo.
    El slug transmisor-de-nivel mezcla radar TDR y ultrasónicos; aquí solo
    contamos filas cuya descripción indica radar/guiado/capacitancia, etc.
    """
    db = get_db()
    col = db[PRODUCTS_COLLECTION]

    pipeline = [
        {
            "$match": {
                "NIVEL_1": {"$regex": "nivel", "$options": "i"},
                "$or": [
                    {
                        "DESCRIPCION_CORTA_PRE": {
                            "$regex": _REGEX_TECNO_PRODUCTO_SOLIDO,
                            "$options": "i",
                        }
                    },
                    {
                        "DESCRIPCION_LARGA_PRE": {
                            "$regex": _REGEX_TECNO_PRODUCTO_SOLIDO,
                            "$options": "i",
                        }
                    },
                ],
                "DESCRIPCION_CORTA_PRE": {
                    "$not": {"$regex": _REGEX_EXCLUIR_PRODUCTO_SOLIDO, "$options": "i"}
                },
            }
        },
        {"$group": {"_id": "$NIVEL_1", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 12},
    ]

    rows = await col.aggregate(pipeline).to_list(12)
    tipos = [
        {"nivel_1": str(row.get("_id") or "").strip(), "count": int(row.get("count") or 0)}
        for row in rows
        if str(row.get("_id") or "").strip()
    ]
    tipos = filtrar_tipos_nivel_1_por_dominio(tipos, "nivel")

    ordenados: list[dict] = []
    vistos: set[str] = set()
    for preferido in _SLUGS_NIVEL_SOLIDO_PRIORIDAD:
        for tipo in tipos:
            slug = str(tipo.get("nivel_1") or "")
            if slug == preferido and slug not in vistos:
                vistos.add(slug)
                ordenados.append(tipo)
    for tipo in tipos:
        slug = str(tipo.get("nivel_1") or "")
        if slug and slug not in vistos:
            vistos.add(slug)
            ordenados.append(tipo)

    logger.info(
        "Tipos NIVEL_1 sólidos/polvo: %s",
        [(t["nivel_1"], t["count"]) for t in ordenados[:6]],
    )
    return ordenados


async def obtener_tipos_radar_nivel(
    respuestas_previas: list[dict],
    texto_extra: str = "",
    extractos_libros: Optional[list[str]] = None,
) -> list[dict]:
    """Tipos NIVEL_1 aptos para sólidos/polvo (cemento, grano…)."""
    ctx = _contexto_material_nivel(respuestas_previas, texto_extra=texto_extra)
    if not ctx.get("es_solido_polvo"):
        from product_discovery import obtener_tipos_nivel_1_por_texto

        partes = [texto_extra]
        for item in respuestas_previas or []:
            partes.append(str(item.get("valor") or ""))
        texto = f"medir nivel tanque silo {' '.join(p for p in partes if p)} radar".strip()
        tipos = await obtener_tipos_nivel_1_por_texto("radar", texto, top=6)
        return filtrar_tipos_nivel_1_por_dominio(tipos, "nivel")[:MAX_OPCIONES]

    tipos = await _tipos_nivel_1_desde_productos_solidos()
    tipos = filtrar_tipos_nivel_1_por_tecnologia(
        tipos,
        respuestas_previas,
        extractos_libros=extractos_libros,
        texto_extra=texto_extra,
    )
    return tipos[:MAX_OPCIONES]


async def afinar_nivel_1_para_contexto(
    nivel_1: Optional[str],
    respuestas_previas: list[dict],
    extractos_libros: Optional[list[str]] = None,
) -> Optional[str]:
    """Ajusta NIVEL_1 para sólidos/polvo sin cambiar la familia elegida por el cliente."""
    ctx = _contexto_material_nivel(respuestas_previas or [])
    if not ctx.get("es_solido_polvo"):
        return nivel_1

    nivel_norm = _normalizar_texto(nivel_1 or "")
    if nivel_norm and "ultrason" in nivel_norm:
        tipos = await obtener_tipos_radar_nivel(
            respuestas_previas,
            texto_extra=nivel_1 or "",
            extractos_libros=extractos_libros,
        )
        if tipos:
            for preferido in _SLUGS_NIVEL_SOLIDO_PRIORIDAD:
                for tipo in tipos:
                    if str(tipo.get("nivel_1") or "") == preferido:
                        return preferido
            return str(tipos[0]["nivel_1"])
        return nivel_1

    if nivel_1:
        return nivel_1

    tipos = await obtener_tipos_radar_nivel(
        respuestas_previas,
        extractos_libros=extractos_libros,
    )
    if tipos:
        for preferido in _SLUGS_NIVEL_SOLIDO_PRIORIDAD:
            for tipo in tipos:
                if str(tipo.get("nivel_1") or "") == preferido:
                    return preferido
        return str(tipos[0]["nivel_1"])

    return nivel_1


def mensaje_asesoria_tecnica_nivel(
    respuestas_previas: list[dict],
    extractos_libros: Optional[list[str]] = None,
    producto: Optional[dict] = None,
) -> str:
    """Nota breve de asesoría técnica (libros + regla cemento/polvo → radar)."""
    ctx = _contexto_material_nivel(respuestas_previas or [])
    if not ctx.get("es_solido_polvo"):
        return ""

    material = (ctx.get("fluido_valor") or "sólidos o polvo").strip()
    partes = [
        f"Para {material} en tanque o silo, el ultrasonido suele fallar por polvo "
        f"en suspensión; prioricé radar guiado (TDR) u opciones aptas para sólidos."
    ]

    if producto:
        bloque = _bloque_tecnologia_item(_bloque_producto(producto))
        if any(term in bloque for term in ("radar", "tdr", "guiad", "onda guiada")):
            partes.append(
                "Este equipo usa radar de onda guiada, adecuado para cemento y polvo."
            )
        elif any(term in bloque for term in ("rotatoria", "capacit", "vibracion")):
            partes.append(
                "Este interruptor es una opción habitual para sólidos a granel en silos."
            )

    for extracto in extractos_libros or []:
        texto = str(extracto or "").strip()
        norm = _normalizar_texto(texto)
        if not texto or len(texto) < 40:
            continue
        if any(w in norm for w in ("radar", "polvo", "solido", "cemento", "ultrason")):
            snippet = texto[:200].rstrip()
            if len(texto) > 200:
                snippet += "…"
            partes.append(f"Referencia técnica: {snippet}")
            break

    return " ".join(partes)


def producto_inadecuado_para_contexto(
    producto: dict,
    respuestas_previas: list[dict],
) -> bool:
    ctx = _contexto_material_nivel(respuestas_previas or [])
    if not ctx.get("es_solido_polvo"):
        return False
    return _producto_es_ultrasonico(producto)


def filtrar_tipos_nivel_1_por_dominio(
    tipos: list[dict],
    dominio: str,
) -> list[dict]:
    return [
        tipo
        for tipo in (tipos or [])
        if _nivel_1_relevante_dominio(str(tipo.get("nivel_1") or ""), dominio)
    ]


def _clave_respuesta_campo(respuestas_previas: list[dict], campo: str) -> str:
    for item in reversed(respuestas_previas):
        if item.get("campo") == campo:
            return str(item.get("clave") or item.get("valor") or "").strip()
    return ""


def _nivel_1_relevante_dominio(nivel_1: str, dominio: str) -> bool:
    n = _normalizar_texto(nivel_1)
    if not n:
        return False

    for term in NIVEL_1_EXCLUIR_POR_DOMINIO.get(dominio, ()):
        if _normalizar_texto(term) in n:
            return False

    incluir = NIVEL_1_INCLUIR_POR_DOMINIO.get(dominio, ())
    if incluir:
        return any(_normalizar_texto(term) in n for term in incluir)

    return True


def filtrar_productos_por_dominio(
    productos: list[dict],
    dominio: str,
) -> list[dict]:
    if not productos or not dominio:
        return productos

    filtrados = [
        p for p in productos
        if _nivel_1_relevante_dominio(
            str(p.get("nivel_1") or p.get("categoria") or ""),
            dominio,
        )
    ]

    if filtrados:
        logger.info(
            "Filtro dominio '%s': %s → %s productos",
            dominio,
            len(productos),
            len(filtrados),
        )
        return filtrados

    return productos


def _niveles_1_contextuales(
    productos: list[dict],
    dominio: str,
    respuestas_previas: list[dict],
    extractos_libros: Optional[list[str]] = None,
) -> list[tuple[str, int]]:
    productos_dom = filtrar_productos_por_dominio(productos, dominio)
    productos_dom = filtrar_productos_por_tecnologia_material(
        productos_dom,
        respuestas_previas,
        extractos_libros=extractos_libros,
    )
    niveles = _niveles_1_frecuentes(productos_dom)
    niveles = [
        (nivel, count)
        for nivel, count in niveles
        if _nivel_1_relevante_dominio(nivel, dominio)
    ]

    aplicacion = _normalizar_texto(_clave_aplicacion(respuestas_previas))
    fluido = _normalizar_texto(_clave_respuesta_campo(respuestas_previas, "fluido"))
    boost_terms = BOOST_NIVEL_1_CONTEXTO.get((dominio, aplicacion, fluido), ())

    if boost_terms and niveles:
        scored: list[tuple[int, int, str]] = []
        for nivel, count in niveles:
            n_norm = _normalizar_texto(nivel)
            boost = sum(1 for term in boost_terms if _normalizar_texto(term) in n_norm)
            scored.append((boost, count, nivel))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        niveles = [(nivel, count) for _, count, nivel in scored[:6]]

    ctx_material = _contexto_material_nivel(respuestas_previas)
    prefer, excluir = _tecnologias_nivel_para_material(ctx_material, extractos_libros)
    niveles = _filtrar_niveles_por_tecnologia(niveles, prefer, excluir)

    return niveles


def generar_pregunta_fluido_material(dominio: str, aplicacion_clave: str) -> Optional[dict]:
    """Segunda pregunta: fluido o material según dónde se mide."""
    opciones_raw = (FLUIDOS_POR_APLICACION.get(dominio) or {}).get(aplicacion_clave)
    if not opciones_raw:
        return None

    contexto = {
        "tanques": "en el tanque",
        "solidos": "en el silo o tolva",
        "liquidos": "en el proceso",
        "vapor": "en la línea o caldera",
        "alimentos": "en el proceso",
        "industrial": "en el proceso",
        "agua": "en la línea",
        "aire": "en la línea",
        "proceso": "en el proceso",
        "laboratorio": "en el laboratorio",
    }.get(aplicacion_clave, "en el proceso")

    return {
        "tipo": "fluido",
        "campo": "fluido",
        "texto": f"¿Qué fluido o material hay {contexto}?",
        "opciones": _construir_opciones_hibridas([etiqueta for _, etiqueta in opciones_raw]),
        "mapa_valores": {etiqueta: clave for clave, etiqueta in opciones_raw},
    }


def generar_pregunta_tipo_instrumento(
    niveles_1: list[tuple[str, int]],
    dominio: str = "",
    respuestas_previas: Optional[list[dict]] = None,
    extractos_libros: Optional[list[str]] = None,
) -> Optional[dict]:
    """Pregunta por familia NIVEL_1 relevante al dominio y contexto."""
    opciones_dominio = {
        "nivel": [
            "interruptores de nivel",
            "transmisores de nivel",
            "medidores de nivel",
        ],
        "temperatura": [
            "termometros bimetalicos",
            "termometros infrarrojos portatiles",
            "controles de temperatura",
        ],
        "presion": [
            "transmisores de presion",
            "manometros con glicerina",
            "transmisores de presion diferencial",
        ],
        "humedad": [
            "transmisores de humedad",
            "medidores de humedad portatiles",
            "termohigrometros",
        ],
        "caudal": [
            "medidores de caudal",
            "rotametros",
            "medidores electromagneticos",
        ],
    }

    niveles_filtrados = [
        (nivel, count)
        for nivel, count in (niveles_1 or [])
        if not dominio or _nivel_1_relevante_dominio(nivel, dominio)
    ]

    ctx_material = _contexto_material_nivel(respuestas_previas or [])
    prefer, excluir = _tecnologias_nivel_para_material(ctx_material, extractos_libros)
    niveles_filtrados = _filtrar_niveles_por_tecnologia(
        niveles_filtrados, prefer, excluir
    )

    if len(niveles_filtrados) >= 2:
        opciones = [
            _formatear_nivel_1(nivel)
            for nivel, _ in niveles_filtrados[:MAX_OPCIONES]
        ]
        mapa = {
            _formatear_nivel_1(nivel): nivel
            for nivel, _ in niveles_filtrados[:MAX_OPCIONES]
        }
    else:
        if dominio == "nivel" and ctx_material.get("es_solido_polvo"):
            if not niveles_filtrados:
                return None
            opciones = [
                _formatear_nivel_1(nivel)
                for nivel, _ in niveles_filtrados[:MAX_OPCIONES]
            ]
            mapa = {
                _formatear_nivel_1(nivel): nivel
                for nivel, _ in niveles_filtrados[:MAX_OPCIONES]
            }
        else:
            fallback = opciones_dominio.get(dominio) or []
            if niveles_filtrados:
                fallback = [_formatear_nivel_1(niveles_filtrados[0][0])] + fallback
            fallback = list(dict.fromkeys(fallback))[:MAX_OPCIONES]
            if not fallback:
                return None
            opciones = fallback
            mapa = {_formatear_nivel_1(o): o.replace(" ", "-") for o in opciones}

    texto = _texto_pregunta_tipo_equipo(
        dominio, respuestas_previas or [], extractos_libros=extractos_libros
    )

    return {
        "tipo": "nivel_1",
        "campo": "nivel_1",
        "texto": texto,
        "opciones": _construir_opciones_hibridas(opciones),
        "mapa_valores": mapa,
    }


def _texto_pregunta_tipo_equipo(
    dominio: str,
    respuestas_previas: list[dict],
    extractos_libros: Optional[list[str]] = None,
) -> str:
    aplicacion = _normalizar_texto(_clave_aplicacion(respuestas_previas))
    fluido = _normalizar_texto(_clave_respuesta_campo(respuestas_previas, "fluido"))
    ctx_material = _contexto_material_nivel(respuestas_previas)

    if dominio == "temperatura" and aplicacion == "alimentos":
        material = {
            "solido": "sólidos o granos",
            "liquido": "líquidos o salsas",
            "ambiente": "ambiente o cámara",
        }.get(fluido, "")
        if material:
            return (
                f"¿Qué tipo de instrumento de temperatura necesitas "
                f"para {material} en alimentos?"
            )
        return "¿Qué tipo de instrumento de temperatura necesitas para alimentos?"

    if dominio == "nivel":
        if ctx_material.get("es_solido_polvo"):
            material = ctx_material.get("fluido_valor") or "sólidos o polvo"
            return (
                f"Para {material} en tanque/silo, lo más adecuado suele ser radar de nivel "
                f"(no ultrasonido en polvo/cemento). ¿Qué tipo de equipo radar necesitas?"
            )
        return "¿Qué tipo de equipo de medición de nivel necesitas?"

    return "¿Qué tipo de equipo de medición necesitas?"


def generar_pregunta_desde_campo(campo_info: dict) -> dict:
    """Pregunta técnica desde atributos discriminantes del pool filtrado."""
    campo = campo_info["campo"]
    ejemplos = campo_info.get("valores_frecuentes") or []
    etiqueta = _etiqueta_campo(campo)
    articulo = _articulo_campo(campo)

    return {
        "tipo": "tecnico",
        "campo": campo,
        "texto": f"¿Cuál es {articulo} {etiqueta} que necesitas?",
        "opciones": _construir_opciones_hibridas(ejemplos),
        "mapa_valores": {},
    }


def resolver_respuesta_hibrida(mensaje: str, pregunta: dict) -> tuple[str, str]:
    """
    Retorna (tipo, valor):
    - opcion: valor de la opción elegida
    - otro: ""
    - texto_libre: texto del cliente
    """
    texto = (mensaje or "").strip()
    texto_lower = _normalizar_texto(texto)
    opciones = pregunta.get("opciones") or []

    if not texto_lower:
        return "otro", ""

    if texto_lower in {"otro", "otra", "ninguno", "ninguna"}:
        return "otro", ""

    if re.fullmatch(r"\d+", texto_lower):
        idx = int(texto_lower)
        valores = [o for o in opciones if o.get("valor") != "otro"]
        if 1 <= idx <= len(valores):
            return "opcion", valores[idx - 1]["valor"]
        if idx == len(opciones):
            return "otro", ""

    mapa = pregunta.get("mapa_valores") or {}
    for etiqueta, clave in mapa.items():
        if _normalizar_texto(etiqueta) in texto_lower or texto_lower in _normalizar_texto(etiqueta):
            return "opcion", etiqueta

    for opcion in opciones:
        label = _normalizar_texto(opcion.get("label") or "")
        if label and (label in texto_lower or texto_lower in label):
            return "opcion", opcion.get("valor") or opcion.get("label") or ""

    return "texto_libre", texto


async def cargar_productos_por_codigos(codigos: list[str]) -> list[dict]:
    if not codigos:
        return []

    db = get_db()
    collection = db[PRODUCTS_COLLECTION]
    cursor = collection.find(
        {"CODIGO": {"$in": codigos}},
        {"_id": 0},
    ).limit(MAX_CANDIDATOS_POOL)

    docs = await cursor.to_list(MAX_CANDIDATOS_POOL)
    return [normalizar_producto(doc) for doc in docs]


def _detectar_dominio_hibrido(texto: str) -> str:
    dominio = _inferir_dominio_tolerante(texto)
    if dominio:
        return dominio

    return "general"


async def buscar_pool_por_dominio(
    dominio: str,
    texto_usuario: str = "",
) -> list[str]:
    """
    Pool inicial con consultas OR por dominio (evita AND estricto de buscar_por_texto).
    """
    db = get_db()
    collection = db[PRODUCTS_COLLECTION]

    terminos: list[str] = []
    vistos: set[str] = set()

    def _agregar(term: str):
        term = str(term or "").strip()
        if len(term) < 3:
            return
        key = _normalizar_texto(term)
        if key in vistos:
            return
        vistos.add(key)
        terminos.append(term)

    t = _normalizar_texto(texto_usuario)
    for token in t.split():
        if token in {"medir", "medicion", "necesito", "quiero", "controlar", "monitorear"}:
            continue
        if len(token) >= 4:
            _agregar(token)

    for term in DOMINIO_TERMINOS_BUSQUEDA.get(dominio, []):
        _agregar(term)

    codigos: list[str] = []
    codigos_vistos: set[str] = set()

    for term in terminos:
        if len(codigos) >= MAX_CANDIDATOS_POOL:
            break

        safe = re.escape(term)
        filtro = {
            "$or": [
                {"NIVEL_1": {"$regex": safe, "$options": "i"}},
                {"NIVEL_2": {"$regex": safe, "$options": "i"}},
                {"NIVEL_3": {"$regex": safe, "$options": "i"}},
                {"NIVEL_4": {"$regex": safe, "$options": "i"}},
                {"texto_busqueda": {"$regex": safe, "$options": "i"}},
                {"DESCRIPCION_CORTA_PRE": {"$regex": safe, "$options": "i"}},
                {"DESCRIPCION_LARGA_PRE": {"$regex": safe, "$options": "i"}},
                {"APLICACIONES": {"$regex": safe, "$options": "i"}},
            ]
        }

        cursor = collection.find(filtro, {"CODIGO": 1, "_id": 0}).limit(
            MAX_CANDIDATOS_POOL - len(codigos)
        )
        docs = await cursor.to_list(MAX_CANDIDATOS_POOL - len(codigos))

        for doc in docs:
            codigo = str(doc.get("CODIGO") or "").strip()
            if codigo and codigo not in codigos_vistos:
                codigos_vistos.add(codigo)
                codigos.append(codigo)

    logger.info(
        "Pool por dominio '%s' terminos=%s candidatos=%s",
        dominio,
        terminos[:6],
        len(codigos),
    )
    return codigos


async def obtener_pool_inicial(texto: str) -> tuple[str, list[str], list[str]]:
    """
    Retorna (dominio, codigos_candidatos, extractos_libros).
    """
    ctx = contexto_para_agente(texto)
    dominio = _detectar_dominio_hibrido(texto)
    extractos = ctx.get("extractos") or []

    if dominio == "nivel":
        ctx_nivel = contexto_para_agente(
            f"{texto} medición nivel tanque silo polvo sólido radar ultrasonido"
        )
        extra = ctx_nivel.get("extractos") or []
        vistos = set(extractos)
        for frag in extra:
            if frag not in vistos:
                extractos.append(frag)
                vistos.add(frag)
        extractos = extractos[:5]

    if dominio == "humedad":
        ctx_humedad = contexto_para_agente(
            f"{texto} humedad punto de rocio termohigrometro transmisor higrometro psicrometro"
        )
        extra = ctx_humedad.get("extractos") or []
        vistos = set(extractos)
        for frag in extra:
            if frag not in vistos:
                extractos.append(frag)
                vistos.add(frag)
        extractos = extractos[:5]

    codigos = await buscar_pool_por_dominio(dominio, texto)

    if not codigos:
        query_limpia = " ".join(DOMINIO_TERMINOS_BUSQUEDA.get(dominio, [])[:2])
        productos = await buscar_por_texto(query_limpia) or []
        for prod in productos[:MAX_CANDIDATOS_POOL]:
            codigo = str(prod.get("codigo") or "").strip()
            if codigo:
                codigos.append(codigo)

    logger.info(
        "Pool híbrido inicial dominio=%s texto='%s' candidatos=%s",
        dominio,
        texto[:80],
        len(codigos),
    )

    return dominio, codigos, extractos[:3]


def _bloque_producto(producto: dict) -> str:
    return " ".join(
        str(producto.get(campo) or "")
        for campo in (
            "nombre",
            "descripcion_corta",
            "descripcion_larga",
            "categoria",
            "nivel_1",
            "nivel_3",
            "texto_busqueda",
        )
    ).lower()


def filtrar_productos_por_respuesta(
    productos: list[dict],
    respuesta: str,
    campo: Optional[str] = None,
) -> list[dict]:
    if not productos:
        return []

    respuesta_norm = _normalizar_texto(respuesta)
    if not respuesta_norm:
        return productos

    tokens = [
        t
        for t in respuesta_norm.split()
        if len(t) >= 3
    ]

    sinonimos_aplicacion = {
        "tanques": ["tanque", "almacenamiento", "deposito", "depósito"],
        "agua": ["agua", "efluente", "liquido", "líquido"],
        "solidos": ["solido", "sólido", "silo", "tolva", "grano", "polvo"],
        "alimentos": ["alimento", "alimentos", "cocina", "food", "grado alimenticio"],
        "industrial": ["industrial", "proceso", "planta"],
        "laboratorio": ["laboratorio", "clinica", "clínica"],
    }

    sinonimos_fluido = {
        "solido": ["solido", "sólido", "grano", "cereal", "masa", "polvo", "granulo", "granel", "cemento", "concreto", "arena", "cal"],
        "granel": ["granel", "cemento", "concreto", "polvo", "solido", "sólido", "arena", "cal", "harina"],
        "liquido": ["liquido", "líquido", "salsa", "fluido"],
        "ambiente": ["ambiente", "camara", "cámara", "aire", "horno"],
        "agua": ["agua", "potable", "residual", "efluente"],
        "aceite": ["aceite", "combustible", "hidrocarburo", "lubricante"],
        "quimico": ["quimico", "químico", "corrosivo", "acido", "álcali"],
    }

    if campo == "aplicacion":
        extra = sinonimos_aplicacion.get(respuesta_norm, [])
        tokens = list(dict.fromkeys(tokens + extra))

    if campo == "fluido":
        extra = sinonimos_fluido.get(respuesta_norm, [])
        tokens = list(dict.fromkeys(tokens + extra))

    filtrados = []
    for producto in productos:
        bloque = _bloque_producto(producto)
        nivel_1 = _normalizar_texto(str(producto.get("nivel_1") or producto.get("categoria") or ""))

        if campo == "nivel_1":
            if respuesta_norm in nivel_1 or any(t in nivel_1 for t in tokens):
                filtrados.append(producto)
            continue

        if any(token in bloque for token in tokens):
            filtrados.append(producto)

    if filtrados:
        logger.info(
            "Filtro híbrido campo=%s respuesta='%s': %s → %s productos",
            campo,
            respuesta[:40],
            len(productos),
            len(filtrados),
        )
        if campo in {"aplicacion", "fluido"}:
            minimo = max(8, int(len(productos) * 0.08))
            if len(filtrados) < minimo:
                logger.info(
                    "Filtro suave campo=%s: se mantiene pool de %s",
                    campo,
                    len(productos),
                )
                return productos
        return filtrados

    return productos


def _niveles_1_frecuentes(productos: list[dict]) -> list[tuple[str, int]]:
    conteo = Counter()
    for producto in productos:
        nivel = str(
            producto.get("nivel_1")
            or producto.get("categoria")
            or producto.get("raw", {}).get("NIVEL_1")
            or ""
        ).strip()
        if nivel:
            conteo[nivel] += 1

    return conteo.most_common(6)


def _campos_discriminantes_pool(productos: list[dict], campos_usados: set[str]) -> list[dict]:
    descripciones = []
    for producto in productos:
        bloque = " ".join(
            str(producto.get(campo) or "")
            for campo in ("descripcion_larga", "descripcion_corta", "nombre")
        )
        if bloque.strip():
            descripciones.append(bloque)

    campos = analizar_campos_discriminantes(descripciones, top_n=4)
    return [c for c in campos if c.get("campo") not in campos_usados]


async def generar_siguiente_pregunta_hibrida(
    dominio: str,
    productos: list[dict],
    respuestas_previas: list[dict],
    campos_usados: set[str],
    extractos_libros: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Elige la siguiente pregunta según estado del pool y respuestas previas.
    Secuencia: dónde → fluido/material → tipo de equipo → dato técnico.
    """
    num = len(respuestas_previas)

    if num == 0:
        return generar_pregunta_aplicacion(dominio)

    if "fluido" not in campos_usados:
        aplicacion_clave = _clave_aplicacion(respuestas_previas)
        pregunta_fluido = generar_pregunta_fluido_material(dominio, aplicacion_clave)
        if pregunta_fluido:
            return pregunta_fluido

    if "nivel_1" not in campos_usados:
        niveles = _niveles_1_contextuales(
            productos, dominio, respuestas_previas, extractos_libros=extractos_libros
        )
        ctx_mat = _contexto_material_nivel(respuestas_previas)
        if dominio == "nivel" and ctx_mat.get("es_solido_polvo"):
            radar_tipos = await obtener_tipos_radar_nivel(
                respuestas_previas,
                extractos_libros=extractos_libros,
            )
            if radar_tipos:
                niveles = [(t["nivel_1"], int(t.get("count") or 0)) for t in radar_tipos]

        pregunta_tipo = generar_pregunta_tipo_instrumento(
            niveles,
            dominio=dominio,
            respuestas_previas=respuestas_previas,
            extractos_libros=extractos_libros,
        )
        if pregunta_tipo:
            return pregunta_tipo

    campos = _campos_discriminantes_pool(productos, campos_usados)
    if campos:
        return generar_pregunta_desde_campo(campos[0])

    return None


def construir_query_acumulado(texto_original: str, respuestas: list[dict]) -> str:
    partes = [texto_original]
    for item in respuestas:
        valor = str(item.get("valor") or "").strip()
        if valor:
            partes.append(valor)
    return " ".join(partes).strip()


def _producto_es_herramienta_construccion(producto: dict) -> bool:
    bloque = _bloque_producto(producto)
    descartes = (
        "guia laser",
        "guía laser",
        "linea cruzada",
        "línea cruzada",
        "pistola radar",
        "radar de velocidad",
        "medidor de velocidad",
    )
    return any(term in bloque for term in descartes)


def seleccionar_producto_final(
    productos: list[dict],
    query: str,
    dominio: str = "",
    respuestas_previas: Optional[list[dict]] = None,
    extractos_libros: Optional[list[str]] = None,
) -> tuple[bool, Optional[dict]]:
    if not productos:
        return False, None

    candidatos = list(productos)
    if dominio == "nivel":
        candidatos = filtrar_productos_por_tecnologia_material(
            candidatos,
            respuestas_previas or [],
            extractos_libros=extractos_libros,
            texto_extra=query,
        )
        industriales = [
            p for p in candidatos
            if not _producto_es_herramienta_construccion(p)
            and _nivel_1_relevante_dominio(
                str(p.get("nivel_1") or p.get("categoria") or ""),
                dominio,
            )
        ]
        if industriales:
            candidatos = industriales

    if len(candidatos) == 1:
        return True, candidatos[0]

    ok, producto = evaluar_coincidencia(
        candidatos,
        query,
        campos=max(2, len(query.split()) // 3),
    )
    return ok, producto
