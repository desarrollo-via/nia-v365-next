"""Prueba presión: no repetir pregunta de rango."""
import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

import main
from product_discovery import generar_preguntas_presion_coherentes, obtener_descripciones_largas_por_nivel_1


async def test_generacion():
    desc = await obtener_descripciones_largas_por_nivel_1("manometros-con-glicerina")
    preguntas = generar_preguntas_presion_coherentes("manometros-con-glicerina", desc)
    textos = [p["texto"] for p in preguntas]
    print("Preguntas:", textos)
    assert len(textos) == 2
    assert textos[0] != textos[1]
    assert "presión" in textos[0].lower()
    assert "conexión" in textos[1].lower() or "carátula" in textos[1].lower()


async def test_flujo():
    sid = f"test_pres_{int(time.time() * 1000)}"
    steps = [
        "necesito medir presion",
        "Líquidos y tanques",
        "Agua",
        "manometros con glicerina",
        "0-200 psi",
    ]
    textos = []
    for msg in steps:
        r = await main.procesar_turno(session_id=sid, phone_id="573001", mensaje=msg)
        t = r.get("respuesta", "")
        textos.append(t)
        print(">>", msg)
        print(t[:200])

    assert textos[-1] != textos[-2] or "conexión" in textos[-1].lower()
    print("OK")


async def run():
    await test_generacion()
    await test_flujo()


if __name__ == "__main__":
    asyncio.run(run())
