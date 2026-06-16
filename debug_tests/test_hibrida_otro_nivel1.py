"""Prueba: Otro en híbrida + termometro digital no reinicia el flujo."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

import main


async def run():
    ctx = {
        "texto_original": "necesito medir temperatura",
        "modo_busqueda": "hibrida_guiada",
        "flujo_descubrimiento": "hibrida_libros",
        "fase_descubrimiento": "esperando_otro_hibrida",
        "dominio": "temperatura",
        "respuestas_hibridas": [
            {"campo": "aplicacion", "valor": "Alimentos y cocina"},
            {"campo": "fluido", "valor": "Sólido o grano"},
        ],
    }
    cliente = {"nombre": "Andres Valencia"}

    resp, etapa, nuevo_ctx = await main._resolver_otro_hibrida(
        necesidad_ctx=ctx,
        mensaje="termometro digital",
        cliente=cliente,
        productos_acumulados=[],
    )

    print("Respuesta:", resp)
    print("Etapa:", etapa)
    print("Fase:", nuevo_ctx.get("fase_descubrimiento"))
    print("Opciones:", [o.get("label") for o in nuevo_ctx.get("opciones_actuales", [])])

    assert "dónde vas a medir" not in resp.lower()
    assert "digital" in resp.lower() or any(
        "digital" in (o.get("label") or "").lower()
        for o in nuevo_ctx.get("opciones_actuales", [])
    )
    assert nuevo_ctx.get("fase_descubrimiento") == "seleccion_tipo_otro"
    print("OK")


if __name__ == "__main__":
    asyncio.run(run())
