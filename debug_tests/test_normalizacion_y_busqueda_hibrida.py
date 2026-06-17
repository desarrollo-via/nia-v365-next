"""
Regresiones de búsqueda de catálogo.

1. Las tildes no deben romper la búsqueda por NIVEL_1.
2. La búsqueda híbrida debe conservar el mensaje original.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from catalog import (
    buscar_con_descubrimiento_producto,
    extraer_campos_tecnicos,
)
from main import _buscar_y_responder_hibrido
from product_discovery import (
    _normalizar_texto,
    obtener_tipos_nivel_1,
)


async def test_termometro_con_tilde() -> None:
    assert (
        _normalizar_texto("termómetro industrial")
        == "termometro industrial"
    )

    tipos = await obtener_tipos_nivel_1(
        "termómetro",
        top=5,
    )

    niveles = [
        _normalizar_texto(
            str(item.get("nivel_1") or "")
        )
        for item in tipos
    ]

    assert niveles, (
        "La búsqueda con tilde debe devolver familias "
        "reales del catálogo."
    )

    assert any(
        "termometro" in nivel
        for nivel in niveles
    ), (
        "Las familias devueltas deben pertenecer "
        "al dominio de termómetros."
    )

    incompatibles = (
        "conectores-industriales-electricos",
        "breakers-industriales-electricos",
        "fuentes-de-alimentacion-industriales",
    )

    assert not any(
        incompatible in nivel
        for nivel in niveles
        for incompatible in incompatibles
    ), (
        "No deben aparecer categorías eléctricas "
        "incompatibles."
    )

    print(
        "OK: termómetro con tilde conserva "
        "su dominio."
    )


async def test_transmisor_hibrido() -> None:
    mensaje = (
        "Necesito un transmisor con entrada "
        "4-20 mA y salida de relé"
    )

    campos = extraer_campos_tecnicos(mensaje)

    respuestas_tecnicas = [
        str(valor).strip()
        for valor in campos.values()
        if str(valor).strip()
    ]

    resultado = await buscar_con_descubrimiento_producto(
        palabra_clave="",
        nivel_1=None,
        respuestas_tecnicas=respuestas_tecnicas,
        texto_original=mensaje,
    )

    producto = resultado.get("producto") or {}

    assert resultado.get("estado") == "encontrado"

    assert str(producto.get("codigo") or "") == "107009", (
        "Debe recuperar el transmisor 107009, "
        "no un controlador PID incompatible."
    )

    source = inspect.getsource(
        _buscar_y_responder_hibrido
    )

    assert "texto_original=mensaje" in source, (
        "main.py debe conservar el mensaje original "
        "en el flujo híbrido."
    )

    print(
        "OK: búsqueda híbrida conserva el texto "
        "original y encuentra 107009."
    )


async def main() -> None:
    await test_termometro_con_tilde()
    await test_transmisor_hibrido()

    print(
        "OK: normalización y búsqueda híbrida "
        "validadas."
    )


if __name__ == "__main__":
    asyncio.run(main())
