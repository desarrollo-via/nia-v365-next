import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from product_discovery import (
    _formatear_nivel_1,
    resolver_tipos_catalogo_inicio,
)
from discovery_guards import preguntas_epi_con_opciones


async def test_resolver_botas_electricidad():
    mensaje = "necesito unas botas para electricidad"
    tipos = await resolver_tipos_catalogo_inicio(
        palabra_clave="botas",
        mensaje=mensaje,
        busqueda_textual=True,
        top=3,
    )
    labels = [_formatear_nivel_1(t["nivel_1"]) for t in tipos]
    print("Tipos:", labels)
    assert tipos, "debe encontrar tipos NIVEL_1"
    assert any("calzado" in t["nivel_1"].lower() for t in tipos)
    assert not any("escalera" in t["nivel_1"].lower() for t in tipos[:1])


def test_preguntas_epi_tienen_opciones():
    preguntas = preguntas_epi_con_opciones("necesito botas para electricidad")
    assert len(preguntas) == 3
    for p in preguntas:
        assert isinstance(p, dict)
        assert p.get("texto")
        assert len(p.get("opciones") or []) >= 3


if __name__ == "__main__":
    asyncio.run(test_resolver_botas_electricidad())
    test_preguntas_epi_tienen_opciones()
    print("OK: test_botas_nivel1_opciones")
