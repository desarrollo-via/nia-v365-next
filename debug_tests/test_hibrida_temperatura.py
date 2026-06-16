"""Prueba flujo temperatura alimentos sólidos — sin manómetros."""
import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

import main


async def turno(session_id: str, mensaje: str):
    r = await main.procesar_turno(
        session_id=session_id,
        phone_id="573001234567",
        mensaje=mensaje,
    )
    return r.get("respuesta", ""), r.get("opciones") or []


async def run():
    sid = f"test_temp_{int(time.time() * 1000)}"
    steps = [
        "necesito medir temperatura",
        "Alimentos y cocina",
        "Sólido o grano",
    ]
    labels = []
    for msg in steps:
        texto, opciones = await turno(sid, msg)
        labels.append([o["label"] for o in opciones])
        print(f">> {msg}")
        print(texto)
        print("opciones:", labels[-1])

    r4, o4 = await turno(sid, labels[-1][0] if labels[-1] else "termometros bimetalicos")
    print(">> equipo")
    print(r4)
    opciones_rango = [o["label"] for o in o4]
    print("opciones:", opciones_rango)

    assert "manometro" not in " ".join(labels[-1]).lower()
    assert "psi" not in " ".join(opciones_rango).lower()
    assert any("°" in l or "c" in l.lower() for l in opciones_rango if o4)
    print("OK")


if __name__ == "__main__":
    asyncio.run(run())
