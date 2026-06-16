"""Simula el turno Otro → 'alimentos' sin API."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from main import (
    _continuar_descubrimiento_corta_larga,
    _en_flujo_corta_larga,
    _try_resolver_turno_corta_larga,
)


async def main():
    ctx = {
        "palabra_clave": "termometro",
        "texto_original": "necesito un termometro",
        "flujo_descubrimiento": "corta_larga",
        "fase_descubrimiento": "esperando_otro_tipo",
        "tipos_catalogo": [],
    }
    cliente = {"nombre": "Andres Valencia"}

    assert _en_flujo_corta_larga(ctx)

    turno = await _try_resolver_turno_corta_larga(
        mensaje="alimentos",
        necesidad_ctx=ctx,
        cliente=cliente,
        productos_acumulados=[],
    )
    assert turno is not None

    respuesta, etapa, ctx_out = turno

    print("etapa:", etapa)
    print("fase:", ctx_out.get("fase_descubrimiento"))
    print("opciones:", ctx_out.get("opciones_actuales"))
    print("respuesta (primeros 500 chars):", respuesta[:500])

    assert etapa == "descubrimiento"
    assert ctx_out.get("fase_descubrimiento") == "seleccion_tipo_otro"
    assert len(ctx_out.get("opciones_actuales") or []) == 4
    assert ctx_out["opciones_actuales"][0]["label"] == "termometros de cocina alimentos"
    assert "Para identificar el producto correcto" not in respuesta
    assert "tipo de alimento" not in respuesta.lower()


if __name__ == "__main__":
    asyncio.run(main())
