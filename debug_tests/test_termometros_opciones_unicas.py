import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from dotenv import load_dotenv

load_dotenv(BASE / ".env")

from product_discovery import (
    _clave_dedup_opcion,
    generar_preguntas_tecnicas_por_nivel_1,
)


async def test_termometros_sin_rangos_repetidos():
    preg = await generar_preguntas_tecnicas_por_nivel_1(
        "termometros-bimetalicos",
        dominio="temperatura",
        contexto_texto="termometro industrial",
    )
    assert len(preg) >= 1
    for pregunta in preg:
        labels = [o["label"] for o in pregunta.get("opciones") or [] if o["label"] != "Otro"]
        claves = [_clave_dedup_opcion(l) for l in labels]
        assert len(claves) == len(set(claves)), (pregunta["texto"], labels)
        print("OK:", pregunta["texto"], labels)


if __name__ == "__main__":
    asyncio.run(test_termometros_sin_rangos_repetidos())
    print("TODOS OK")
