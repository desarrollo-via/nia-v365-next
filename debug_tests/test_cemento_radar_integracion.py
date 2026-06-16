"""Integración: cemento → transmisor-de-nivel → producto radar (no ultrasónico)."""
import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv

load_dotenv(BASE / ".env")

from hybrid_discovery import (
    obtener_tipos_radar_nivel,
    afinar_nivel_1_para_contexto,
    producto_inadecuado_para_contexto,
    mensaje_asesoria_tecnica_nivel,
)
from catalog import buscar_con_descubrimiento_producto


async def test_tipos_radar_cemento():
    resp = [
        {"campo": "aplicacion", "clave": "tanques", "valor": "Tanques de almacenamiento"},
        {"campo": "fluido", "clave": "granel", "valor": "cemento"},
    ]
    tipos = await obtener_tipos_radar_nivel(resp)
    slugs = [t["nivel_1"] for t in tipos]
    assert "transmisor-de-nivel" in slugs, slugs
    assert len(slugs) >= 2, f"Debe ofrecer 2+ opciones radar, obtuvo: {slugs}"
    print("OK tipos radar:", slugs)


async def test_afinar_mantiene_transmisor():
    resp = [
        {"campo": "fluido", "clave": "granel", "valor": "cemento"},
    ]
    afin = await afinar_nivel_1_para_contexto("transmisor-de-nivel", resp)
    assert afin == "transmisor-de-nivel"
    print("OK afinar mantiene transmisor-de-nivel")


async def test_busqueda_final_radar():
    resp = [
        {"campo": "aplicacion", "clave": "tanques", "valor": "Tanques de almacenamiento"},
        {"campo": "fluido", "clave": "granel", "valor": "cemento"},
        {"campo": "nivel_1", "clave": "transmisor-de-nivel", "valor": "transmisor de nivel"},
    ]
    res = await buscar_con_descubrimiento_producto(
        palabra_clave="nivel",
        nivel_1="transmisor-de-nivel",
        respuestas_tecnicas=["Hasta 2 metros", "4-20mA"],
        respuestas_hibridas_previas=resp,
    )
    producto = res.get("producto") or {}
    codigo = producto.get("codigo") or ""
    nombre = (producto.get("nombre") or "").lower()
    assert res.get("estado") in ("encontrado", "relacionado"), res
    assert producto_inadecuado_para_contexto(producto, resp) is False, (
        f"Producto inadecuado: {codigo} {nombre}"
    )
    assert "ultrason" not in nombre, f"Ultrasonico elegido: {codigo} {nombre}"
    assert any(t in nombre for t in ("radar", "guiad", "tdr", "onda guiada")), (
        f"No es radar: {codigo} {nombre}"
    )
    nota = mensaje_asesoria_tecnica_nivel(resp, producto=producto)
    assert "ultrasonido" in nota.lower()
    print("OK producto radar:", codigo, nombre[:60])
    print("OK asesoria:", nota[:100], "…")


async def main():
    await test_tipos_radar_cemento()
    await test_afinar_mantiene_transmisor()
    await test_busqueda_final_radar()
    print("TODOS OK")


if __name__ == "__main__":
    asyncio.run(main())
