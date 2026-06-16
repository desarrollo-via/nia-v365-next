import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from main import (
    _ctx_confirmacion_producto,
    _es_confirmacion_afirmativa,
    _es_confirmacion_negativa,
    construir_respuesta_desde_resultado,
)


def test_opciones_confirmacion_producto():
    ctx = _ctx_confirmacion_producto()
    opciones = ctx.get("opciones_actuales") or []

    assert len(opciones) == 2
    assert opciones[0]["label"] == "Sí"
    assert opciones[0]["valor"] == "sí"
    assert opciones[1]["label"] == "No"
    assert opciones[1]["valor"] == "no"


def test_botones_si_no_reconocidos():
    assert _es_confirmacion_afirmativa("sí")
    assert _es_confirmacion_negativa("no")


def test_construir_respuesta_incluye_opciones():
    productos = []
    res = {
        "estado": "encontrado",
        "producto": {
            "codigo": "P242049",
            "nombre": "psicrometro",
            "marca": "proskit",
        },
    }

    _, etapa, ctx = construir_respuesta_desde_resultado(
        res=res,
        cliente={"nombre": "Andres"},
        productos_acumulados=productos,
        desde="test",
        necesidad_ctx_base={"dominio": "humedad"},
    )

    assert etapa == "producto_encontrado"
    assert len(ctx.get("opciones_actuales") or []) == 2


if __name__ == "__main__":
    test_opciones_confirmacion_producto()
    test_botones_si_no_reconocidos()
    test_construir_respuesta_incluye_opciones()
    print("OK: test_confirmacion_botones")
