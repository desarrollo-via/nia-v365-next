"""Prueba: nivel + tanques + otro + cemento → radar/transmisor, no láser construcción."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

import main
from hybrid_discovery import (
    _inferir_clave_material,
    filtrar_tipos_nivel_1_por_dominio,
    obtener_pool_inicial,
    cargar_productos_por_codigos,
    generar_siguiente_pregunta_hibrida,
)


async def test_cemento_sigue_hibrida():
    ctx = {
        "texto_original": "necesito medir nivel",
        "dominio": "nivel",
        "flujo_descubrimiento": "hibrida_libros",
        "fase_descubrimiento": "preguntas_hibridas",
        "pregunta_actual": {
            "campo": "fluido",
            "texto": "¿Qué fluido o material hay en el tanque?",
            "opciones": [],
        },
        "respuestas_hibridas": [
            {"campo": "aplicacion", "valor": "Tanques de almacenamiento", "clave": "tanques"},
        ],
        "campos_usados": {"aplicacion"},
        "preguntas_realizadas": 1,
    }
    dominio, codigos, _ = await obtener_pool_inicial("necesito medir nivel")
    ctx["candidatos_codigos"] = codigos
    ctx["dominio"] = dominio

    cliente = {"nombre": "Andres Valencia"}
    resp, etapa, nuevo = await main._continuar_hibrida_guiada(
        necesidad_ctx=ctx,
        mensaje="otro",
        cliente=cliente,
        productos_acumulados=[],
    )
    assert nuevo.get("fase_descubrimiento") == "esperando_texto_hibrida"
    print("Paso otro fluido OK")

    resp2, _, ctx2 = await main._continuar_hibrida_guiada(
        necesidad_ctx=nuevo,
        mensaje="cemento",
        cliente=cliente,
        productos_acumulados=[],
    )
    print("Tras cemento:", resp2)
    opciones = [o.get("label", "") for o in ctx2.get("opciones_actuales", [])]
    print("Opciones tipo equipo:", opciones)

    assert "dónde vas a medir" not in resp2.lower()
    assert opciones, "debe preguntar tipo de equipo"
    joined = " ".join(opciones).lower()
    assert "radar" in joined or "ultrason" in joined or "transmisor" in joined
    assert "laser" not in joined or "guia" not in joined
    print("OK cemento -> tipo radar/transmisor")


async def test_filtro_nivel_1():
    from product_discovery import obtener_tipos_nivel_1_por_texto, _formatear_nivel_1

    raw = await obtener_tipos_nivel_1_por_texto(
        "transmisor",
        "necesito medir nivel tanques cemento radar",
        top=6,
    )
    filtrados = filtrar_tipos_nivel_1_por_dominio(raw, "nivel")
    labels = [_formatear_nivel_1(t["nivel_1"]) for t in filtrados[:3]]
    print("NIVEL_1 filtrados:", labels)
    assert labels
    assert "laser" not in labels[0].lower()
    print("OK filtro NIVEL_1")


async def run():
    assert _inferir_clave_material("cemento") == "granel"
    await test_filtro_nivel_1()
    await test_cemento_sigue_hibrida()
    print("TODOS OK")


if __name__ == "__main__":
    asyncio.run(run())
