"""
knowledge.py — Base de conocimiento técnico de NIA
Carga los JSONL de Creus y Kuphaldt al arrancar y los mantiene en memoria.
Expone búsqueda por dominio para alimentar al agente de preguntas.
"""

import json
import logging
import os
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Dict, Optional

logger = logging.getLogger("nia.knowledge")

# Rutas candidatas (en orden de prioridad)
_PROJECT_DIR = Path(__file__).resolve().parent
_WORKSPACE_DIR = _PROJECT_DIR.parent

_LOCAL_DIR = _PROJECT_DIR / "conocimiento"
_FALLBACK_DIR = _WORKSPACE_DIR / "nia-mongo-main" / "knowledge" / "industrial_books"


def _resolver_archivo_conocimiento(nombre: str) -> Optional[Path]:
    """
    Resuelve la ruta de un archivo de conocimiento.

    Orden:
    1. Variable de entorno KNOWLEDGE_DIR / KNOWLEDGE_RAG_FILE
    2. nia-v365-main/conocimiento/
    3. nia-mongo-main/knowledge/industrial_books/ (copia existente en el repo)
    """
    env_dir = os.getenv("KNOWLEDGE_DIR")
    if env_dir:
        candidato = Path(env_dir) / nombre
        if candidato.exists():
            return candidato

    if nombre == "book_rag_ready_all.jsonl":
        env_rag = os.getenv("KNOWLEDGE_RAG_FILE")
        if env_rag and Path(env_rag).exists():
            return Path(env_rag)

    for base in (_LOCAL_DIR, _FALLBACK_DIR):
        candidato = base / nombre
        if candidato.exists():
            return candidato

    return None


RAG_FILE = _resolver_archivo_conocimiento("book_rag_ready_all.jsonl")
CONC_FILE = _resolver_archivo_conocimiento("book_concepts_all.jsonl")

# ─── Mapeo de palabras clave → dominio ───────────────────────────────────────
DOMINIO_KEYWORDS = {
    "transmisores":               ["transmisor", "transmitter", "4-20ma", "hart", "fieldbus"],
    "presion":                    ["presión", "pressure", "manómetro", "manometer", "psi", "bar", "pascal"],
    "temperatura":                ["temperatura", "temperature", "termopar", "thermocouple", "rtd", "pt100"],
    "nivel":                      ["nivel", "level", "tanque", "tank", "ultrasonido", "radar", "tdr", "flotador"],
    "caudal":                     ["caudal", "flujo", "flow", "medidor", "caudalímetro", "flowmeter"],
    "humedad":                    [
        "humedad", "humidity", "rocío", "rocio", "punto de rocío", "punto de rocio",
        "dew point", "termohigrómetro", "termohigrometro", "higrómetro", "higrometro",
        "psicrómetro", "psicrometro",
    ],
    "valvulas_control":           ["válvula", "valve", "actuador", "actuator", "control valve"],
    "control_pid":                ["pid", "controlador", "controller", "lazo", "loop", "setpoint"],
    "analitica_proceso":          ["ph", "conductividad", "oxígeno", "disuelto", "turbidez", "analyzer"],
    "plc_automatizacion":         ["plc", "scada", "hmi", "automatización", "automation", "siemens", "allen"],
    "calibracion":                ["calibración", "calibration", "patrón", "trazabilidad", "span", "zero"],
    "comunicaciones_industriales":["modbus", "profibus", "devicenet", "ethernet", "protocolo", "protocol"],
    "seguridad_funcional":        ["sil", "safety", "seguridad", "iec 61511", "iec 61508", "funcional"],
    "vibracion_mantenimiento":    ["vibración", "vibration", "mantenimiento", "predictivo", "bearing"],
}

# ─── Carga en memoria al importar ────────────────────────────────────────────
_chunks:   List[Dict] = []
_concepts: List[Dict] = []


def _derivar_conceptos_desde_chunks(chunks: List[Dict]) -> List[Dict]:
    """Genera términos por dominio si no existe book_concepts_all.jsonl."""
    vistos: set[tuple[str, str]] = set()
    conceptos: List[Dict] = []

    for chunk in chunks:
        dominio = chunk.get("domain") or "general"
        metadata = chunk.get("metadata") or {}

        candidatos = list(metadata.get("technical_terms") or [])
        candidatos.extend(metadata.get("signals") or [])
        candidatos.extend(metadata.get("units") or [])

        for termino in candidatos:
            termino_txt = str(termino or "").strip()
            if not termino_txt or len(termino_txt) < 2:
                continue

            clave = (dominio, termino_txt.lower())
            if clave in vistos:
                continue

            vistos.add(clave)
            conceptos.append({"domain": dominio, "term": termino_txt})

    return conceptos


def _cargar():
    global _chunks, _concepts
    if _chunks:
        return

    if RAG_FILE and RAG_FILE.exists():
        with open(RAG_FILE, encoding="utf-8") as f:
            _chunks = [json.loads(linea) for linea in f if linea.strip()]
        logger.info(
            "Conocimiento RAG cargado: %s chunks desde %s",
            len(_chunks),
            RAG_FILE,
        )
    else:
        logger.warning(
            "No se encontró book_rag_ready_all.jsonl. "
            "Colócalo en nia-v365-main/conocimiento/ o define KNOWLEDGE_RAG_FILE."
        )

    if CONC_FILE and CONC_FILE.exists():
        with open(CONC_FILE, encoding="utf-8") as f:
            _concepts = [json.loads(linea) for linea in f if linea.strip()]
        logger.info("Conceptos cargados: %s desde %s", len(_concepts), CONC_FILE)
    elif _chunks:
        _concepts = _derivar_conceptos_desde_chunks(_chunks)
        logger.info(
            "book_concepts_all.jsonl no encontrado; derivados %s conceptos desde RAG",
            len(_concepts),
        )


def estado_conocimiento() -> dict:
    """Estado de carga para diagnóstico."""
    return {
        "rag_file": str(RAG_FILE) if RAG_FILE else None,
        "concepts_file": str(CONC_FILE) if CONC_FILE else None,
        "chunks_cargados": len(_chunks),
        "conceptos_cargados": len(_concepts),
        "fuentes": sorted(
            {
                c.get("source_id")
                for c in _chunks
                if c.get("source_id")
            }
        ),
    }

_cargar()

# ─── Detección de dominio ─────────────────────────────────────────────────────
def detectar_dominio(texto: str) -> Optional[str]:
    """
    Detecta el dominio técnico más probable dado el texto del cliente.
    Retorna el nombre del dominio o None si no hay coincidencia clara.
    """
    texto_lower = texto.lower()
    scores = {}
    for dominio, keywords in DOMINIO_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in texto_lower)
        if score > 0:
            scores[dominio] = score
    return max(scores, key=scores.get) if scores else None

# ─── Búsqueda de chunks relevantes ───────────────────────────────────────────
def buscar_contexto(texto: str, top_k: int = 5) -> List[Dict]:
    """
    Busca los chunks más relevantes para el texto dado.
    Primero filtra por dominio, luego rankea por similitud textual.
    """
    dominio = detectar_dominio(texto)
    pool    = [c for c in _chunks if c.get("domain") == dominio] if dominio else _chunks

    if not pool:
        pool = _chunks

    # Rankea por similitud del texto de búsqueda
    scored = []
    for chunk in pool:
        sim = SequenceMatcher(
            None,
            texto.lower(),
            (chunk.get("text") or chunk.get("search_text") or "").lower()[:500]
        ).ratio()
        scored.append((sim, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]

# ─── Conceptos del dominio ────────────────────────────────────────────────────
def conceptos_del_dominio(dominio: str, top_k: int = 10) -> List[str]:
    """Retorna los términos técnicos más relevantes de un dominio."""
    return [
        c["term"] for c in _concepts
        if c.get("domain") == dominio
    ][:top_k]

# ─── Resumen de contexto para el agente ──────────────────────────────────────
def contexto_para_agente(texto: str) -> dict:
    """
    Prepara el contexto completo que necesita questions_agent.py:
    - dominio detectado
    - chunks relevantes
    - términos técnicos del dominio
    """
    dominio = detectar_dominio(texto)
    chunks  = buscar_contexto(texto, top_k=4)
    terminos = conceptos_del_dominio(dominio, top_k=8) if dominio else []

    extractos = []
    for c in chunks:
        txt = (c.get("text") or "")[:400]
        if txt.strip():
            extractos.append(txt)

    return {
        "dominio":   dominio or "general",
        "extractos": extractos,
        "terminos":  terminos,
    }
