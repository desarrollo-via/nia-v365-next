"""Prueba flujo híbrido nivel: dónde → fluido → equipo."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

import main
from hybrid_discovery import generar_pregunta_aplicacion, generar_pregunta_fluido_material


async def turno(session_id: str, mensaje: str):
    r = await main.procesar_turno(
        session_id=session_id,
        phone_id="573001234567",
        mensaje=mensaje,
    )
    return r.get("respuesta", ""), r.get("opciones") or []


import time

async def run():
    sid = f"test_flujo_nivel_{int(time.time() * 1000)}"
    r1, o1 = await turno(sid, "necesito medir nivel")
    print("P1:", r1)
    assert "dónde vas a medir el nivel" in r1.lower()

    r2, o2 = await turno(sid, "Tanques de almacenamiento")
    print("P2:", r2)
    assert "fluido o material" in r2.lower()

    r3, o3 = await turno(sid, "Agua")
    print("P3:", r3)
    assert "tipo de equipo" in r3.lower()

    r4, o4 = await turno(sid, "interruptores de nivel")
    print("P4:", r4)
    print("O4:", [o["label"] for o in o4])
    assert "referencia exacta" in r4.lower()
    assert "altura del tanque" in r4.lower() or "rango de nivel" in r4.lower()
    assert "temperatura" not in r4.lower()
    assert len(o4) > 0

    r5, o5 = await turno(sid, "2 a 5 metros")
    print("P5:", r5)
    assert "temperatura" not in r5.lower()
    assert "presión" in r5.lower() or "montaje" in r5.lower() or "salida" in r5.lower()
    print("OK")


if __name__ == "__main__":
    asyncio.run(run())
