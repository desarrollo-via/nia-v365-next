"""Prueba: 2+ palabras usan similitud textual en NIVEL_1."""
import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

import main
from product_discovery import _formatear_nivel_1, obtener_tipos_nivel_1_por_texto


async def test_ranking_termometro_digital():
    tipos = await obtener_tipos_nivel_1_por_texto("termometro", "termometro digital", top=3)
    labels = [_formatear_nivel_1(t["nivel_1"]) for t in tipos]
    print("Ranking:", labels)
    assert labels, "sin resultados"
    assert "digital" in labels[0].lower()
    assert "bimetal" not in labels[0].lower()
    print("OK ranking")


async def test_flujo_inicio_termometro_digital():
    sid = f"test_textual_{int(time.time() * 1000)}"
    r = await main.procesar_turno(
        session_id=sid,
        phone_id="573001234567",
        mensaje="termometro digital",
    )
    respuesta = r.get("respuesta", "")
    opciones = r.get("opciones") or []
    labels = [o.get("label", "") for o in opciones]
    print("Respuesta:", respuesta)
    print("Opciones:", labels)

    assert "termometro digital" in respuesta.lower() or "cercanos" in respuesta.lower()
    assert labels, "sin opciones"
    assert "digital" in labels[0].lower()
    assert not any("bimetal" in l.lower() for l in labels[:2])
    print("OK flujo")


if __name__ == "__main__":
    asyncio.run(test_ranking_termometro_digital())
    asyncio.run(test_flujo_inicio_termometro_digital())
    print("TODOS OK")
