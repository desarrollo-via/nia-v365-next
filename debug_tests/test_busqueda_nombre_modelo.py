import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from dotenv import load_dotenv

load_dotenv(BASE / ".env")

from main import detectar_identificador, detectar_modo_busqueda, buscar_en_catalogo


async def test_profipack_no_extrae_c400():
    tipo, valor = detectar_identificador("ProfiPack C400")
    assert tipo is None and valor is None, (tipo, valor)
    assert detectar_modo_busqueda("ProfiPack C400") != "codigo_exacto"
    res = await buscar_en_catalogo("ProfiPack C400")
    assert res.get("estado") == "encontrado", res
    assert res["producto"].get("codigo") == "P245366"
    print("OK ProfiPack C400 -> P245366")


async def test_codigo_p_sigue_funcionando():
    tipo, valor = detectar_identificador("p245366")
    assert tipo == "referencia" and valor == "P245366"
    assert detectar_modo_busqueda("p245366") == "codigo_exacto"
    print("OK p245366 sigue como codigo exacto")


if __name__ == "__main__":
    asyncio.run(test_profipack_no_extrae_c400())
    asyncio.run(test_codigo_p_sigue_funcionando())
    print("TODOS OK")
