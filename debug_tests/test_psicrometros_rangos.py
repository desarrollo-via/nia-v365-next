import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from dotenv import load_dotenv
load_dotenv(BASE / ".env")
from product_discovery import generar_preguntas_tecnicas_por_nivel_1


async def test_psicrometros_tienen_rangos():
    preg = await generar_preguntas_tecnicas_por_nivel_1(
        "psicrometros",
        dominio="humedad",
        contexto_texto="punto de rocio ambiente",
    )
    assert len(preg) >= 1
    opts = [o["label"] for o in preg[0].get("opciones") or []]
    assert "Otro" in opts
    assert len(opts) >= 3, opts
    assert "rocío" in preg[0]["texto"].lower() or "rocio" in preg[0]["texto"].lower()
    print("OK Q1:", preg[0]["texto"], opts)
    opts2 = [o["label"] for o in preg[1].get("opciones") or []]
    assert len(opts2) >= 3, opts2
    print("OK Q2:", preg[1]["texto"], opts2)


if __name__ == "__main__":
    asyncio.run(test_psicrometros_tienen_rangos())
    print("TODOS OK")
